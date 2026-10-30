"""Envia cargas fictícias periódicas à API; não cria uma tarefa permanente."""
import argparse
import json
import time
import urllib.request


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--iterations', type=int, default=6)
    parser.add_argument('--interval', type=float, default=10)
    parser.add_argument('--seed', type=int, default=9000)
    parser.add_argument('--url', default='http://127.0.0.1:5088')
    args = parser.parse_args()
    if not 1 <= args.iterations <= 1000 or not 0 <= args.interval <= 3600:
        parser.error('iterations: 1..1000; interval: 0..3600 segundos')
    for i in range(args.iterations):
        scenario = ('normal', 'high_rejection', 'normal', 'source_failure')[i % 4]
        payload = {'seed': args.seed + i, 'count': 150, 'component': i % 8, 'scenario': scenario}
        request = urllib.request.Request(args.url.rstrip('/') + '/api/runs', data=json.dumps(payload).encode(),
                                         headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(request, timeout=70) as response:
            print(response.read().decode(), flush=True)
        if i < args.iterations - 1:
            time.sleep(args.interval)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        pass
