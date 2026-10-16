"""Build an allowlisted CF upload package; excludes environments, recordings and secrets."""
import argparse
import hashlib
import json
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('output', type=Path)
    parser.add_argument('--stage-models', action='store_true', help='Download pinned models during CF staging instead of uploading weights')
    args = parser.parse_args()
    subprocess.run([sys.executable, str(ROOT/'scripts/download_models.py'), '--verify'], check=True)
    models = json.loads((ROOT/'models/checksums.json').read_text('utf-8'))
    names = ['LICENSE', 'THIRD_PARTY_NOTICES.md', 'Procfile', 'run.py', 'runtime.txt', 'requirements.txt', 'requirements-linux.lock',
             'models.lock.json', 'models/checksums.json', 'scripts/download_models.py']
    if not args.stage_models:
        names.extend('models/' + name for name in models['sha256'])
    for directory in ('app', 'licenses', 'cf-model-stage'):
        names.extend(p.relative_to(ROOT).as_posix() for p in (ROOT/directory).rglob('*')
                     if p.is_file() and '__pycache__' not in p.parts and p.suffix in {'.py','.js','.html','.css','.txt','.toml'})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(args.output, 'w', zipfile.ZIP_DEFLATED, compresslevel=1) as archive:
        for name in sorted(set(names)):
            if name == 'requirements.txt' and not args.stage_models:
                requirements = (ROOT/name).read_text('utf-8-sig').replace('./cf-model-stage', '')
                archive.writestr(name, requirements)
            else:
                archive.write(ROOT/name, name)
    size = args.output.stat().st_size
    if size > 1_500_000_000:
        raise ValueError('CF package exceeds SAP BTP 1.5 GB limit')
    with args.output.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    print(json.dumps({'package':str(args.output.resolve()), 'bytes':size, 'sha256':digest, 'files':len(set(names))}, indent=2))


if __name__ == '__main__':
    main()
