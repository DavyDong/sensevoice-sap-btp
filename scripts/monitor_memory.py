import argparse
import json
import time
from pathlib import Path

import psutil

parser = argparse.ArgumentParser()
parser.add_argument('pid', type=int)
parser.add_argument('--seconds', type=int, default=300)
parser.add_argument('--out', type=Path, default=Path('reports/memory.json'))
args = parser.parse_args()
process = psutil.Process(args.pid)
peak = 0
values = []
started = time.monotonic()
try:
    while time.monotonic() - started < args.seconds:
        processes = [process] + process.children(recursive=True)
        memories = [p.memory_info() for p in processes if p.is_running()]
        rss = sum(m.rss for m in memories)
        peak = max(peak, rss, sum(getattr(m, 'peak_wset', m.rss) for m in memories))
        values.append(round(rss / 2**20, 1))
        time.sleep(.1)
except (psutil.NoSuchProcess, KeyboardInterrupt):
    pass
args.out.parent.mkdir(parents=True, exist_ok=True)
args.out.write_text(json.dumps({'pid':args.pid,'includes_child_processes':True,'sample_interval_ms':100,'seconds':round(time.monotonic()-started,1),'peak_rss_mib':round(peak/2**20,1),'last_rss_mib':values[-1] if values else None}, indent=2), 'utf-8')
print(args.out.read_text('utf-8'))
