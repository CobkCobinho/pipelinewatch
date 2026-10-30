"""Integração HTTP real com Kestrel e Python, em um banco descartável."""
import csv
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request

from pipelinewatch.core import demo

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(os.getenv('PIPELINEWATCH_API_TESTS') == '1', 'Ative PIPELINEWATCH_API_TESTS=1 após compilar a API')
class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        directory = ROOT / '.runtime/tests'
        directory.mkdir(parents=True, exist_ok=True)
        cls.temp = tempfile.TemporaryDirectory(dir=directory)
        cls.root = Path(cls.temp.name)
        demo(cls.root, batches=24)
        cls.base = 'http://127.0.0.1:5098'
        dll = ROOT / 'api/PipelineWatch.Api/bin/Release/net10.0/PipelineWatch.Api.dll'
        cls.log = (ROOT / '.runtime/api-test.log').open('w', encoding='utf-8')
        cls.process = subprocess.Popen(['dotnet', str(dll), '--urls', cls.base,
                                        '--PipelineWatch:Root', str(cls.root), '--Python:Executable', sys.executable],
                                       cwd=ROOT, stdout=cls.log, stderr=subprocess.STDOUT)
        try:
            deadline = time.monotonic() + 20
            while True:
                try:
                    with urllib.request.urlopen(cls.base + '/health', timeout=1):
                        break
                except (OSError, urllib.error.URLError):
                    if time.monotonic() >= deadline or cls.process.poll() is not None:
                        raise RuntimeError('API de teste não iniciou')
                    time.sleep(0.1)
        except BaseException:
            cls.process.terminate()
            cls.process.wait(timeout=10)
            cls.temp.cleanup()
            raise

    @classmethod
    def tearDownClass(cls):
        cls.process.terminate()
        cls.process.wait(timeout=10)
        cls.log.close()
        cls.temp.cleanup()

    def request(self, path, payload=None):
        request = urllib.request.Request(self.base + path, data=None if payload is None else json.dumps(payload).encode(),
                                         headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(request, timeout=15) as response:
            return response.status, response.read().decode('utf-8-sig')

    def test_summary_matches_csv_and_preserves_volume(self):
        _, text = self.request('/api/summary')
        summary = json.loads(text)
        _, text = self.request('/api/powerbi/runs')
        rows = list(csv.DictReader(io.StringIO(text)))
        self.assertEqual(summary['executions'], len(rows))
        self.assertEqual(summary['inputRows'], summary['acceptedRows'] + summary['rejectedRows'])
        self.assertEqual(summary['acceptedRows'], sum(int(r['accepted_rows']) for r in rows))
        self.assertTrue(summary['synthetic'])

    def test_run_detail_graph_and_not_found(self):
        _, text = self.request('/api/runs?limit=2')
        runs = json.loads(text)
        self.assertEqual(len(runs), 2)
        run_id = runs[0]['run_id']
        _, text = self.request('/api/runs/' + run_id)
        self.assertEqual(len(json.loads(text)['events']), 6)
        _, text = self.request('/api/graph?runId=' + run_id)
        graph = json.loads(text)
        self.assertEqual(len(graph['nodes']), 6)
        self.assertEqual(len(graph['edges']), 5)
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.request('/api/runs/00000000-0000-0000-0000-000000000000')
        self.assertEqual(error.exception.code, 404)

    def test_rejects_invalid_input_and_arbitrary_exports(self):
        for path, payload, expected in [('/api/runs?limit=0', None, 400),
                                         ('/api/powerbi/secrets', None, 404),
                                         ('/api/runs', {'count': 10001}, 400),
                                         ('/api/runs', {'scenario': 'command'}, 400)]:
            with self.subTest(path=path, payload=payload):
                with self.assertRaises(urllib.error.HTTPError) as error:
                    self.request(path, payload)
                self.assertEqual(error.exception.code, expected)

    def test_post_executes_python_and_refreshes_exports(self):
        _, before = self.request('/api/summary')
        status, text = self.request('/api/runs', {'seed': 42, 'count': 20, 'component': 2, 'scenario': 'high_rejection'})
        self.assertEqual(status, 201)
        run = json.loads(text)
        self.assertEqual(run['input_rows'], 20)
        _, after = self.request('/api/summary')
        self.assertEqual(json.loads(after)['executions'], json.loads(before)['executions'] + 1)
        self.request('/api/runs/' + run['run_id'])


if __name__ == '__main__':
    unittest.main()
