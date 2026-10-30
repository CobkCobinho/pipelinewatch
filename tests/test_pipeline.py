import csv
import io
import json
import math
import tempfile
import unittest
from datetime import date
from pathlib import Path

from pipelinewatch.core import COMPONENTS, EDGES, STAGES, connect, demo, export, generate, run_pipeline, validate


class PipelineTests(unittest.TestCase):
    def setUp(self):
        temporary_root = Path(__file__).resolve().parents[1] / '.runtime' / 'tests'
        temporary_root.mkdir(parents=True, exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(dir=temporary_root)
        self.root = Path(self.temporary.name)

    def tearDown(self):
        self.temporary.cleanup()

    def test_generator_is_reproducible_and_never_needs_company_data(self):
        a = generate(7, 200, date(2026, 10, 1))
        self.assertEqual(a, generate(7, 200, date(2026, 10, 1)))
        self.assertTrue(all(row["lot"].startswith("DEMO-") for row in a))

    def test_valid_records_pass_and_duplicates_are_rejected(self):
        row = generate(1, 1, date(2026, 10, 1), error_rate=0)[0]
        seen = set()
        self.assertEqual(validate(row, seen, date(2026, 10, 1)), [])
        self.assertIn("Duplicidade", [e[0] for e in validate(row, seen, date(2026, 10, 1))])

    def test_boundaries_and_nonfinite_numbers(self):
        original = generate(1, 1, date(2026, 10, 1), error_rate=0)[0]
        for field, value in (("quantity", 0), ("quantity", 1.5), ("quantity", True),
                             ("voltage_v", math.nan), ("temperature_c", math.inf),
                             ("temperature_c", 126), ("supplier", " "),
                             ("component_code", "REAL-COMPANY-PART"),
                             ("inspection_date", "2026-10-02")):
            with self.subTest(field=field, value=value):
                self.assertTrue(validate({**original, field: value}, set(), date(2026, 10, 1)))
        self.assertFalse(validate({**original, "voltage_v": 10.8, "temperature_c": -40}, set(), date(2026, 10, 1)))

    def test_sql_counts_reconcile_with_quarantine(self):
        result = run_pipeline(self.root, seed=51, count=250, scenario="high_rejection")
        self.assertEqual(result["input_rows"], result["accepted_rows"] + result["rejected_rows"])
        self.assertGreater(result["rejected_rows"], 0)
        with connect(self.root) as con:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM accepted_records").fetchone()[0], result["accepted_rows"])
            self.assertEqual(con.execute("SELECT COUNT(*) FROM rejected_records").fetchone()[0], result["rejected_rows"])
            self.assertGreaterEqual(con.execute("SELECT COUNT(*) FROM quality_errors").fetchone()[0], result["rejected_rows"])
            self.assertEqual(con.execute("SELECT COUNT(*) FROM stage_events").fetchone()[0], 6)

    def test_source_failure_marks_downstream_as_skipped(self):
        result = run_pipeline(self.root, scenario="source_failure")
        self.assertEqual(result["status"], "Falha")
        with connect(self.root) as con:
            statuses = [r[0] for r in con.execute("SELECT status FROM stage_events ORDER BY stage_index")]
            self.assertEqual(statuses, ["Falha"] + ["Ignorada"] * 5)

    def test_export_preserves_headers_and_real_denominators(self):
        snapshot = export(self.root)
        self.assertEqual(snapshot["runs"], [])
        self.assertIn("run_id", (self.root / "data/gold/runs.csv").read_text())
        run_pipeline(self.root, scenario="source_failure")
        snapshot = export(self.root)
        self.assertIsNone(snapshot["runs"][0]["quality_pct"])
        self.assertTrue(snapshot["metadata"]["synthetic"])
        self.assertEqual(json.loads((self.root / "data/gold/snapshot.json").read_text(encoding="utf-8")), snapshot)

    def test_demo_has_all_families_statuses_and_valid_edges(self):
        snapshot = demo(self.root, batches=24, end_date=date(2026, 10, 30))
        self.assertEqual(len(snapshot["runs"]), 24)
        self.assertEqual({r["component_family"] for r in snapshot["runs"]}, {c[2] for c in COMPONENTS})
        self.assertEqual({r["status"] for r in snapshot["runs"]}, {"Sucesso", "Alerta", "Falha"})
        self.assertTrue(all(a in STAGES and b in STAGES for a, b in EDGES))
        with connect(self.root) as con:
            self.assertEqual(con.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            self.assertEqual(con.execute("PRAGMA foreign_key_check").fetchall(), [])
        for table in ("runs", "events", "errors", "daily", "components"):
            with (self.root / f"data/gold/{table}.csv").open(encoding="utf-8", newline="") as handle:
                self.assertEqual(len(list(csv.DictReader(handle))), len(snapshot[table]))

    def test_invalid_input_does_not_create_partial_run(self):
        for args in ({"count": 0}, {"count": 10001}, {"component_index": 99}, {"scenario": "unsafe"}):
            with self.subTest(args=args), self.assertRaises(ValueError):
                run_pipeline(self.root, **args)
        with connect(self.root) as con:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM runs").fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()
