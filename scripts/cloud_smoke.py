"""Real CF/XSUAA integration. Credentials stay in memory and are never written to reports."""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]


def cf_json(path):
    wrapper = os.getenv('ASR_CF_WRAPPER')
    command = ['pwsh', '-NoProfile', '-File', wrapper] if wrapper else ['cf']
    result = subprocess.run(command + ['curl', path], capture_output=True, text=True, check=True)
    return json.loads(result.stdout)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--app', default='sensevoice-asr')
    parser.add_argument('--space-guid', required=True)
    parser.add_argument('--service', default='sensevoice-xsuaa')
    args = parser.parse_args()
    apps = cf_json(f'/v3/apps?names={args.app}&space_guids={args.space_guid}')['resources']
    if len(apps) != 1:
        raise ValueError('Expected exactly one app in the requested space')
    guid = apps[0]['guid']
    routes = cf_json(f'/v3/apps/{guid}/routes')['resources']
    if len(routes) != 1:
        raise ValueError('Select one route before testing')
    base = 'https://' + routes[0]['url']
    binding = cf_json(f'/v3/apps/{guid}/env')['system_env_json']['VCAP_SERVICES']['xsuaa']
    credentials = next(b['credentials'] for b in binding if b['name'] == args.service)
    report = {'app':args.app, 'app_guid':guid, 'url':base, 'checks':{}}
    with httpx.Client(timeout=120, trust_env=False) as client:
        token_response = client.post(credentials['url'].rstrip('/') + '/oauth/token',
                                     auth=(credentials['clientid'], credentials['clientsecret']),
                                     data={'grant_type':'client_credentials'})
        token_response.raise_for_status()
        token = token_response.json()['access_token']
        report['oauth'] = {'grant_type':'client_credentials', 'status':token_response.status_code,
                           'expires_in':token_response.json().get('expires_in')}
        for name, path, headers, expected in [
            ('ready', '/health/ready', {}, 200),
            ('missing_token', '/v1/transcribe', {}, 401),
            ('invalid_token', '/v1/transcribe', {'Authorization':'Bearer invalid'}, 401),
            ('untrusted_origin', '/v1/transcribe', {'Authorization':'Bearer '+token,'Origin':'https://invalid.example'}, 403),
        ]:
            response = client.get(base+path) if name == 'ready' else client.post(base+path, headers=headers)
            report['checks'][name] = {'status':response.status_code, 'expected':expected}
            assert response.status_code == expected, f'{name}: status {response.status_code}'
        response = client.get(base+'/')
        assert response.status_code == 200 and 'SenseVoice' in response.text
        report['checks']['web_page'] = {'status':response.status_code}
    environment = os.environ.copy()
    environment['ASR_ACCESS_TOKEN'] = token
    subprocess.run([sys.executable, str(ROOT/'scripts/smoke_test.py'), '--url', base,
                    '--report', str(ROOT/'reports/cloud-real-smoke.json')], env=environment, check=True)
    processes = cf_json(f'/v3/apps/{guid}/processes')['resources']
    for process in processes:
        if process['type'] == 'web':
            report['process'] = {k:process[k] for k in ('guid','memory_in_mb','disk_in_mb','instances')}
            report['stats'] = [{k:item[k] for k in ('state','routable','uptime','mem_quota','disk_quota','usage')}
                               for item in cf_json(f"/v3/processes/{process['guid']}/stats")['resources']]
    (ROOT/'reports/cloud-validation.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), 'utf-8')
    print(json.dumps({'url':base, 'checks':report['checks'], 'oauth':report['oauth']}, indent=2))


if __name__ == '__main__':
    main()
