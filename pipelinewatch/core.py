"""Geração, validação, armazenamento SQL e exportação. Somente biblioteca padrão."""

from __future__ import annotations

import csv
import io
import json
import math
import os
import random
import sqlite3
import tempfile
import time
import uuid
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPONENTS = (
    ("ECU-100", "Unidade de controle eletrônico", "ECUs", 12.0),
    ("ABS-210", "Módulo eletrônico de frenagem", "Módulos ABS", 12.0),
    ("SEN-320", "Sensor de posição", "Sensores", 5.0),
    ("HAR-410", "Chicote de alimentação", "Chicotes", 12.0),
    ("PCB-510", "Placa de controle", "Placas", 5.0),
    ("CON-610", "Conector de baixa tensão", "Conectores", 12.0),
    ("REL-710", "Relé de acionamento", "Relés", 12.0),
    ("FUS-810", "Fusível de proteção", "Fusíveis", 12.0),
)
CATALOG = {item[0]: item for item in COMPONENTS}
PLANTS = ("Aurora Engenharia — fictícia", "Horizonte Lab — fictício", "Vale Circuitos — fictícia")
STAGES = ("Gerar", "Bronze", "Validar", "Silver", "Gold", "Quarentena")
EDGES = (("Gerar", "Bronze"), ("Bronze", "Validar"), ("Validar", "Silver"),
         ("Silver", "Gold"), ("Validar", "Quarentena"))
FIELDS = ("record_id", "component_code", "supplier", "lot", "quantity", "voltage_v",
          "temperature_c", "inspection_date")
SCENARIOS = ("normal", "high_rejection", "source_failure")


class ManagedConnection(sqlite3.Connection):
    def __exit__(self, exc_type, exc_value, traceback):
        try:
            return super().__exit__(exc_type, exc_value, traceback)
        finally:
            self.close()


def connect(root: Path = ROOT) -> sqlite3.Connection:
    (root / "data").mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(root / "data/pipelinewatch.db", timeout=30, factory=ManagedConnection)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    con.execute("PRAGMA journal_mode=WAL")
    con.executescript((ROOT / "sql/schema.sql").read_text(encoding="utf-8"))
    con.executemany("INSERT OR IGNORE INTO components VALUES (?,?,?,?)", COMPONENTS)
    con.commit()
    return con


def generate(seed: int, count: int, event_date: date, component_index: int = 0,
             error_rate: float = 0.04) -> list[dict]:
    """Reproduzível para os mesmos argumentos; nenhum arquivo externo é lido."""
    if not 1 <= count <= 10_000:
        raise ValueError("count deve estar entre 1 e 10000")
    if not math.isfinite(error_rate) or not 0 <= error_rate <= 0.5:
        raise ValueError("error_rate deve estar entre 0 e 0.5")
    if not 0 <= component_index < len(COMPONENTS):
        raise ValueError("componente desconhecido")
    rng = random.Random(seed)
    code, _, _, nominal = COMPONENTS[component_index]
    rows = []
    for i in range(count):
        row = {
            "record_id": f"SIM-{seed}-{i:05d}", "component_code": code,
            "supplier": rng.choice(("Atlas Demo", "Órion Demo", "Vértice Demo")),
            "lot": f"DEMO-{event_date:%Y%m%d}-{component_index:02d}",
            "quantity": rng.randint(1, 250),
            "voltage_v": round(nominal * rng.uniform(0.96, 1.04), 3),
            "temperature_c": round(rng.uniform(18, 65), 2),
            "inspection_date": event_date.isoformat(),
        }
        if rng.random() < error_rate:
            fault = rng.choice(("duplicate", "quantity", "supplier", "voltage", "temperature", "code", "date"))
            if fault == "duplicate" and rows:
                row = rows[0].copy()
            elif fault == "quantity":
                row["quantity"] = -1
            elif fault == "supplier":
                row["supplier"] = ""
            elif fault == "voltage":
                row["voltage_v"] = round(nominal * 1.7, 2)
            elif fault == "temperature":
                row["temperature_c"] = 180
            elif fault == "code":
                row["component_code"] = "DESCONHECIDO"
            else:
                row["inspection_date"] = (event_date + timedelta(days=20)).isoformat()
        rows.append(row)
    return rows


def validate(row: dict, seen: set[str], reference_date: date) -> list[tuple[str, str, str]]:
    errors = []

    def reject(rule, field, message):
        errors.append((rule, field, message))

    record_id = str(row.get("record_id") or "").strip()
    if not record_id:
        reject("Identificador ausente", "record_id", "Identificador obrigatório.")
    elif record_id in seen:
        reject("Duplicidade", "record_id", "Identificador já recebido neste lote.")
    if record_id:
        seen.add(record_id)
    component = CATALOG.get(row.get("component_code"))
    if component is None:
        reject("Componente desconhecido", "component_code", "Código fora do catálogo fictício.")
    for field in ("supplier", "lot"):
        if not str(row.get(field) or "").strip():
            reject("Campo obrigatório", field, "Valor obrigatório não preenchido.")
    quantity = row.get("quantity")
    try:
        number = float(quantity)
        if isinstance(quantity, bool) or not math.isfinite(number) or not number.is_integer() or number <= 0:
            raise ValueError()
    except (ValueError, TypeError, OverflowError):
        reject("Quantidade inválida", "quantity", "Quantidade deve ser um inteiro positivo.")
    for field, lower, upper, rule in (
        ("voltage_v", component[3] * 0.9 if component else 0,
         component[3] * 1.1 if component else 60, "Tensão fora da faixa"),
        ("temperature_c", -40, 125, "Temperatura fora da faixa"),
    ):
        try:
            value = float(row.get(field))
            if isinstance(row.get(field), bool) or not math.isfinite(value) or not lower <= value <= upper:
                raise ValueError()
        except (ValueError, TypeError, OverflowError):
            reject(rule, field, f"Valor fora do intervalo fictício [{lower:g}, {upper:g}].")
    try:
        inspection_date = date.fromisoformat(str(row.get("inspection_date")))
        if inspection_date > reference_date:
            raise ValueError()
    except (ValueError, TypeError):
        reject("Data inválida", "inspection_date", "Data inválida ou posterior à data do lote.")
    return errors


def run_pipeline(root: Path = ROOT, *, seed: int = 42, count: int = 200,
                 event_date: date | None = None, component_index: int = 0,
                 scenario: str = "normal") -> dict:
    if scenario not in SCENARIOS:
        raise ValueError("cenário desconhecido")
    if not 1 <= count <= 10_000 or not 0 <= component_index < len(COMPONENTS):
        raise ValueError("volume ou componente inválido")
    event_date = event_date or datetime.now(timezone.utc).date()
    measured_start = time.perf_counter()
    rng = random.Random(seed + 900)
    run_id = str(uuid.uuid4())
    code, _, family, _ = COMPONENTS[component_index]
    rows = [] if scenario == "source_failure" else generate(
        seed, count, event_date, component_index, 0.28 if scenario == "high_rejection" else 0.04)
    raw_path = root / "data/bronze" / f"{run_id}.csv"
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    with raw_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    accepted, rejected, issues = [], [], []
    seen: set[str] = set()
    for number, row in enumerate(rows, 1):
        errors = validate(row, seen, event_date)
        if errors:
            rejected.append((run_id, number, row.get("record_id"), json.dumps(row, ensure_ascii=False)))
            issues.extend((run_id, number, row.get("record_id"), *error) for error in errors)
        else:
            accepted.append((run_id, row["record_id"], row["component_code"], row["supplier"],
                             row["lot"], int(row["quantity"]), float(row["voltage_v"]),
                             float(row["temperature_c"]), row["inspection_date"]))
    failed = scenario == "source_failure"
    if failed:
        issues.append((run_id, None, None, "Fonte indisponível (simulada)", "source", "Falha injetada exclusivamente para demonstração."))
    status = "Falha" if failed else "Alerta" if len(rejected) > len(rows) * 0.05 else "Sucesso"
    durations = [rng.randint(200, 900), rng.randint(200, 1300), rng.randint(800, 3200),
                 rng.randint(400, 1800), rng.randint(200, 1200), rng.randint(100, 800)]
    events = []
    for i, stage in enumerate(STAGES):
        if failed:
            stage_status, incoming, outgoing, reject_count = ("Falha" if i == 0 else "Ignorada"), 0, 0, 0
            duration = durations[0] if i == 0 else 0
        else:
            stage_status = "Alerta" if stage in ("Validar", "Quarentena") and rejected else "Sucesso"
            incoming = 0 if i == 0 else len(rows) if i < 3 else len(rejected) if i == 5 else len(accepted)
            outgoing = len(rows) if i < 2 else len(rejected) if i == 5 else len(accepted)
            reject_count = len(rejected) if i == 2 else 0
            duration = durations[i]
        events.append((run_id, stage, i + 1, stage_status, incoming, outgoing, reject_count, duration))
    duration_ms = sum(e[-1] for e in events[:5])  # Quarentena é um ramo paralelo.
    with connect(root) as con:
        con.execute("BEGIN IMMEDIATE")
        con.execute("INSERT INTO runs VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (
            run_id, event_date.isoformat(), datetime.now(timezone.utc).isoformat(),
            ("Recebimento eletrônico", "Inspeção de bancada", "Rastreabilidade de lotes")[seed % 3],
            family, PLANTS[seed % len(PLANTS)], scenario, seed, status, len(rows),
            len(accepted), len(rejected), len(issues), duration_ms,
            round((time.perf_counter() - measured_start) * 1000, 3)))
        con.executemany("INSERT INTO accepted_records VALUES (?,?,?,?,?,?,?,?,?)", accepted)
        con.executemany("INSERT INTO rejected_records VALUES (?,?,?,?)", rejected)
        con.executemany("INSERT INTO quality_errors(run_id,row_number,record_id,rule_name,field,message) VALUES (?,?,?,?,?,?)", issues)
        con.executemany("INSERT INTO stage_events VALUES (?,?,?,?,?,?,?,?)", events)
    return {"run_id": run_id, "status": status, "input_rows": len(rows),
            "accepted_rows": len(accepted), "rejected_rows": len(rejected)}


def atomic_write(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(dir=path.parent, prefix=".publish-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def export(root: Path = ROOT) -> dict:
    """Uma única leitura SQL produz um snapshot JSON consistente para a API."""
    with connect(root) as con:
        con.execute("BEGIN")
        snapshot = {name: [dict(r) for r in con.execute(f"SELECT * FROM {view}")]
                    for name, view in (("runs", "v_runs"), ("events", "v_events"),
                                       ("errors", "v_errors"), ("daily", "v_daily"),
                                       ("components", "components"))}
    snapshot["metadata"] = {
        "synthetic": True, "organization": "Aurora Engenharia — demonstração fictícia",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "duration_note": "duration_ms é telemetria simulada; measured_ms é o tempo local do processamento, sem exportação.",
        "edges": [{"source": a, "target": b} for a, b in EDGES],
    }
    for name in ("runs", "events", "errors", "daily", "components"):
        rows = snapshot[name]
        if not rows:
            with connect(root) as con:
                view = {"runs": "v_runs", "events": "v_events", "errors": "v_errors",
                        "daily": "v_daily", "components": "components"}[name]
                columns = [item[0] for item in con.execute(f"SELECT * FROM {view} LIMIT 0").description]
        else:
            columns = list(rows[0])
        buffer = io.StringIO(newline="")
        writer = csv.DictWriter(buffer, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)
        atomic_write(root / f"data/gold/{name}.csv", buffer.getvalue())
    atomic_write(root / "data/gold/snapshot.json", json.dumps(snapshot, ensure_ascii=False, allow_nan=False))
    return snapshot


def demo(root: Path = ROOT, batches: int = 72, seed: int = 2026,
         end_date: date | None = None) -> dict:
    if not 1 <= batches <= 1000:
        raise ValueError("batches deve estar entre 1 e 1000")
    end_date = end_date or datetime.now(timezone.utc).date()
    for i in range(batches):
        scenario = "source_failure" if i % 17 == 0 else "high_rejection" if i % 5 == 0 else "normal"
        run_pipeline(root, seed=seed + i, count=120 + (i * 37) % 240,
                     event_date=end_date - timedelta(days=(batches - 1 - i) // 3),
                     component_index=i % len(COMPONENTS), scenario=scenario)
    return export(root)
