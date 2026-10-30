"""Inicializa uma demonstração vazia uma vez e inicia a API local."""
import argparse
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=5088)
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error('Use uma porta entre 1024 e 65535')
    if not (ROOT / 'data/pipelinewatch.db').exists():
        subprocess.run([sys.executable, '-m', 'pipelinewatch', 'demo'], cwd=ROOT, check=True)
    else:
        subprocess.run([sys.executable, '-m', 'pipelinewatch', 'export'], cwd=ROOT, check=True)
    print('Abra powerbi/PipelineWatch.pbip no Power BI Desktop e clique em Atualizar.', flush=True)
    print('Ctrl+C encerra a API. Dados 100% sintéticos.', flush=True)
    subprocess.run(['dotnet', 'run', '--project', str(ROOT / 'api/PipelineWatch.Api'), '-c', 'Release',
                    '--no-launch-profile', '--', '--urls', f'http://127.0.0.1:{args.port}',
                    '--Python:Executable', sys.executable], cwd=ROOT, check=True)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        pass
