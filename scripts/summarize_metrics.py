import os
import sys
import json
from collections import defaultdict
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOGS_DIR = os.path.join(BASE_DIR, 'logs')
METRICS_FILE = os.path.join(LOGS_DIR, 'rpc_metrics.json')


def load_lines(path: str):
    if not os.path.exists(path):
        print(f"Arquivo de métricas não encontrado: {path}")
        sys.exit(1)
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except Exception:
                continue


def summarize(path: str = METRICS_FILE):
    first: dict[str, dict] = {}
    last: dict[str, dict] = {}
    first_ts = None
    last_ts = None

    for rec in load_lines(path):
        ts = rec.get('ts')
        if first_ts is None:
            first_ts = ts
        last_ts = ts
        metrics = rec.get('metrics', {}) or {}
        for url, m in metrics.items():
            if url not in first:
                first[url] = dict(m)
            last[url] = dict(m)

    if not last:
        print('Nenhuma métrica encontrada no arquivo.')
        return 0

    print('Resumo de métricas por provider (janela analisada):')
    if first_ts and last_ts:
        print(f"- Início: {datetime.fromtimestamp(first_ts)} | Fim: {datetime.fromtimestamp(last_ts)} | Duração: {round(last_ts-first_ts,1)}s")
    rows = []
    for url in sorted(last.keys()):
        f = first.get(url, {})
        l = last.get(url, {})
        delta_switch = int(l.get('switches', 0)) - int(f.get('switches', 0))
        delta_fail = int(l.get('fails', 0)) - int(f.get('fails', 0))
        rows.append({
            'url': url,
            'avg_ms': float(l.get('avg_ms', 0.0)),
            'last_ms': float(l.get('last_ms', 0.0)),
            'pings': int(l.get('pings', 0)),
            'fails': int(l.get('fails', 0)),
            'switches': int(l.get('switches', 0)),
            'delta_fails': delta_fail,
            'delta_switches': delta_switch,
        })

    rows.sort(key=lambda r: (r['avg_ms'], r['fails']))
    for r in rows:
        print(f"* {r['url']}")
        print(f"    avg_ms={r['avg_ms']:.1f} last_ms={r['last_ms']:.1f} pings={r['pings']} fails={r['fails']}(+{r['delta_fails']}) switches={r['switches']}(+{r['delta_switches']})")

    # Sugestão simples: menor avg_ms e menor delta_fails -> preferível
    best = rows[0]
    print('\nSugestão: provider preferível (latência/estabilidade):')
    print(f"- {best['url']} (avg_ms={best['avg_ms']:.1f}, delta_fails={best['delta_fails']})")
    return 0


if __name__ == '__main__':
    sys.exit(summarize())
