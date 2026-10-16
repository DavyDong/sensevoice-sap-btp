"""Optional official China mirror for the large SenseVoice weight; verify against the HF pin."""
import concurrent.futures
import json
import math
import time
import urllib.request
from pathlib import Path

from download_models import ROOT, digest

model = json.loads((ROOT/'models.lock.json').read_text('utf-8'))['sensevoice']
with urllib.request.urlopen(f"https://huggingface.co/api/models/{model['repo']}/revision/{model['revision']}?blobs=true", timeout=60) as response:
    metadata = json.load(response)
entry = next(s for s in metadata['siblings'] if s['rfilename'] == 'model.pt')
expected = entry['lfs']['sha256']
size = entry['lfs']['size']
target = ROOT/'models'/'sensevoice'/'model.pt'
parts = ROOT/'.cache'/'model-parts'
parts.mkdir(parents=True, exist_ok=True)
url = 'https://modelscope.cn/models/iic/SenseVoiceSmall/resolve/master/model.pt'
chunk_size = 16*1024*1024


def part(index):
    start, end = index*chunk_size, min(size, (index+1)*chunk_size)-1
    path = parts/f'{index:04d}.part'
    if path.exists() and path.stat().st_size == end-start+1:
        return path
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={'Range':f'bytes={start}-{end}'})
            with urllib.request.urlopen(req, timeout=120) as source, path.open('wb') as output:
                if source.status != 206 or source.headers.get('Content-Range') != f'bytes {start}-{end}/{size}':
                    raise ValueError('Mirror does not honor the requested byte range')
                while data := source.read(1024*1024):
                    output.write(data)
            if path.stat().st_size != end-start+1:
                raise ValueError('Incomplete download')
            print(f'Part {index+1}/{math.ceil(size/chunk_size)} complete', flush=True)
            return path
        except Exception:
            if attempt == 2:
                raise
            time.sleep(attempt+1)


with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
    files = list(pool.map(part, range(math.ceil(size/chunk_size))))
target.parent.mkdir(parents=True, exist_ok=True)
temporary = target.with_suffix('.verified-part')
with temporary.open('wb') as output:
    for path in files:
        with path.open('rb') as source:
            while data := source.read(1024*1024):
                output.write(data)
if digest(temporary) != expected:
    raise ValueError('Mirror weight differs from pinned official model; refusing to use it')
temporary.replace(target)
for path in files:
    path.unlink()
print('Official mirror weight matches the pinned SHA256. Run download_models.py to finish other files.')
