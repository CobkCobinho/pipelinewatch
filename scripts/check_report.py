"""Confere vínculos das medidas, campos e limites das páginas PBIR."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / 'powerbi'


def main():
    model = json.loads((ROOT / 'PipelineWatch.SemanticModel/model.bim').read_text(encoding='utf-8-sig'))['model']
    tables = {t['name']: t for t in model['tables']}
    count = 0

    def check_bindings(node):
        if isinstance(node, dict):
            for kind in ('Column', 'Measure'):
                if kind in node:
                    expr = node[kind]
                    table = tables[expr['Expression']['SourceRef']['Entity']]
                    assert expr['Property'] in {f['name'] for f in table['columns' if kind == 'Column' else 'measures']}, expr
            for value in node.values():
                check_bindings(value)
        elif isinstance(node, list):
            for value in node:
                check_bindings(value)

    for path in (ROOT / 'PipelineWatch.Report/definition/pages').glob('*/page.json'):
        page = json.loads(path.read_text(encoding='utf-8-sig'))
        for visual_path in path.parent.glob('visuals/*/visual.json'):
            visual = json.loads(visual_path.read_text(encoding='utf-8-sig'))
            check_bindings(visual)
            p = visual['position']
            assert 0 <= p['x'] and p['x'] + p['width'] <= page['width']
            assert 0 <= p['y'] and p['y'] + p['height'] <= page['height']
            count += 1
    assert count >= 30
    print(f'{count} visuais: campos, medidas e limites verificados. A renderização requer Power BI Desktop.')


if __name__ == '__main__':
    main()
