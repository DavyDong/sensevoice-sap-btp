"""Download pinned official weights only. No remote Python is downloaded or executed."""
import argparse
import hashlib
import json
import os
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def fetch(url, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + '.part')
    for attempt in range(3):
        try:
            with urllib.request.urlopen(url, timeout=90) as source, temporary.open('wb') as destination:
                size = 0
                while data := source.read(1024 * 1024):
                    destination.write(data)
                    size += len(data)
                    if size % (32 * 1024 * 1024) == 0:
                        print(f'{target.name}: {size // 1024 // 1024} MiB', flush=True)
            temporary.replace(target)
            return
        except Exception:
            if attempt == 2:
                raise
            time.sleep(2 * (attempt + 1))


def digest(path, algorithm='sha256', git_blob=False):
    h = hashlib.new(algorithm)
    if git_blob:
        h.update(f'blob {path.stat().st_size}\0'.encode())
    with path.open('rb') as stream:
        while block := stream.read(1024 * 1024):
            h.update(block)
    return h.hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, default=ROOT / 'models')
    parser.add_argument('--verify', action='store_true')
    args = parser.parse_args()
    lock = json.loads((ROOT / 'models.lock.json').read_text('utf-8'))
    manifest_file = args.root / 'checksums.json'
    if args.verify:
        manifest = json.loads(manifest_file.read_text('utf-8'))
        if manifest['models'] != lock:
            raise ValueError('Model revision lock has changed; download again')
        expected = {f'{name}/{f}' for name, model in lock.items() for f in model['files']}
        if not expected <= set(manifest['sha256']):
            raise ValueError('Incomplete model checksum manifest')
        for name, expected_digest in manifest['sha256'].items():
            if digest(args.root / name) != expected_digest:
                raise ValueError(f'Model checksum mismatch: {name}')
        print('All model files verified.')
        return
    checksums = {}

    def download_model(item):
        directory, model = item
        repo, revision = model['repo'], model['revision']
        url = f'https://huggingface.co/api/models/{repo}/revision/{revision}?blobs=true'
        with urllib.request.urlopen(url, timeout=90) as response:
            metadata = json.load(response)
        if metadata['sha'] != revision:
            raise ValueError('Unexpected upstream revision')
        entries = {s['rfilename']: s for s in metadata['siblings']}
        result = {}
        for name in model['files']:
            entry = entries[name]
            target = args.root / directory / name
            lfs = entry.get('lfs')
            expected = lfs['sha256'] if lfs else entry['blobId']
            algorithm = 'sha256' if lfs else 'sha1'
            valid = target.is_file() and digest(target, algorithm, not lfs) == expected
            if not valid:
                print(f'Downloading {repo}/{name}', flush=True)
                fetch(f'https://huggingface.co/{repo}/resolve/{revision}/{name}', target)
            if digest(target, algorithm, not lfs) != expected:
                raise ValueError(f'Upstream checksum mismatch: {name}')
            result[f'{directory}/{name}'] = digest(target)
        return result

    with ThreadPoolExecutor(max_workers=2) as pool:
        for result in pool.map(download_model, lock.items()):
            checksums.update(result)
    manifest_file.write_text(json.dumps({'models': lock, 'sha256': checksums}, indent=2), 'utf-8')
    print('Models downloaded, pinned revisions and upstream checksums verified.', flush=True)


if __name__ == '__main__':
    main()
