import json
import time

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException

from app.auth import Auth
from app.settings import Settings

STATIC_TOKEN = 'unit-test-only-static-token-' + 'a' * 24


@pytest.fixture
def auth_and_token(monkeypatch):
    monkeypatch.setenv('ACCESS_TOKEN', STATIC_TOKEN)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public = key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    credentials = {'clientid':'sb-test!t1', 'clientsecret':'unit-test-only', 'xsappname':'test!t1',
                   'identityzoneid':'unit-tenant', 'url':'https://unit.example', 'uaadomain':'unit.example', 'verificationkey':public}
    monkeypatch.setenv('VCAP_SERVICES', json.dumps({'xsuaa':[{'name':'sensevoice-xsuaa','credentials':credentials}]}))
    auth = Auth(Settings(auth_mode='xsuaa'))
    base = {'iss':'https://unit.example/oauth/token', 'zid':'unit-tenant', 'exp':int(time.time())+300,
            'iat':int(time.time()), 'aud':['test!t1'], 'cid':'sb-test!t1', 'client_id':'sb-test!t1',
            'sub':'sb-test!t1', 'grant_type':'client_credentials', 'scope':['test!t1.Transcribe']}

    def token(**changes):
        return 'Bearer ' + jwt.encode(dict(base, **changes), key, algorithm='RS256')
    return auth, token


def test_real_signed_token(auth_and_token):
    auth, token = auth_and_token
    assert auth.verify(token()) > time.time()


@pytest.mark.parametrize('changes,code', [
    ({'exp':1},401), ({'aud':['wrong']},401), ({'zid':'wrong'},401),
    ({'iss':'https://wrong/oauth/token'},401), ({'scope':[]},403),
])
def test_claim_failures(auth_and_token, changes, code):
    auth, token = auth_and_token
    with pytest.raises(HTTPException) as error:
        auth.verify(token(**changes))
    assert error.value.status_code == code


def test_invalid_signature_and_missing_token(auth_and_token):
    auth, token = auth_and_token
    signed = token()
    for value in ('', 'Bearer malformed', 'Bearer 中文', 'Bearer \ud800', signed.rsplit('.',1)[0]+'.invalid'):
        with pytest.raises(HTTPException) as error:
            auth.verify(value)
        assert error.value.status_code == 401


def test_static_token_and_rotation(auth_and_token, monkeypatch):
    auth, token = auth_and_token
    assert auth.verify('Bearer ' + STATIC_TOKEN) == float('inf')
    assert auth.verify(token()) > time.time()
    new_value = 'unit-test-only-rotated-token-' + 'b' * 24
    monkeypatch.setenv('ACCESS_TOKEN', new_value)
    rotated = Auth(Settings(auth_mode='xsuaa'))
    assert rotated.verify('Bearer ' + new_value) == float('inf')
    with pytest.raises(HTTPException) as error:
        rotated.verify('Bearer ' + STATIC_TOKEN)
    assert error.value.status_code == 401
    assert rotated.verify(token()) > time.time()
    # The existing process retains its startup configuration until restart.
    assert auth.verify('Bearer ' + STATIC_TOKEN) == float('inf')


def test_empty_static_token_disabled(auth_and_token, monkeypatch):
    _, token = auth_and_token
    monkeypatch.setenv('ACCESS_TOKEN', '')
    auth = Auth(Settings(auth_mode='xsuaa'))
    assert auth.verify(token()) > time.time()
    for value in ('', 'Bearer ', 'Bearer ' + STATIC_TOKEN, 'Basic ' + STATIC_TOKEN, 'Bearer 中文'):
        with pytest.raises(HTTPException) as error:
            auth.verify(value)
        assert error.value.status_code == 401


@pytest.mark.parametrize('value', ['short', ' ' * 32, 'a' * 31, 'a' * 257, 'a' * 32 + '\n', '中' * 32])
def test_invalid_static_configuration(value, monkeypatch):
    monkeypatch.delenv('VCAP_APPLICATION', raising=False)
    with pytest.raises(ValueError, match='ACCESS_TOKEN must be') as error:
        Settings(auth_mode='xsuaa', access_token=value).validate()
    assert value not in str(error.value)


def test_static_config_redacted_and_binding_still_required(monkeypatch):
    settings = Settings(auth_mode='xsuaa', access_token=STATIC_TOKEN)
    assert STATIC_TOKEN not in repr(settings)
    monkeypatch.setenv('VCAP_SERVICES', '{}')
    with pytest.raises(ValueError, match='binding'):
        Auth(settings)


@pytest.fixture
def cloud_client(auth_and_token, monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import create_app

    class Stream:
        def feed(self, data, final=False):
            return [{'type':'segment','text':'test','final':True}] if final else []

    class Engine:
        def __init__(self, settings):
            pass
        def transcribe(self, samples, language):
            return {'text':'test','language':language}
        def new_stream(self, language):
            return Stream()

    monkeypatch.setenv('VCAP_APPLICATION', json.dumps({'application_uris':['unit.example']}))
    with TestClient(create_app(Settings(auth_mode='xsuaa',host='0.0.0.0'),Engine), base_url='https://unit.example') as client:
        yield client, auth_and_token[1]


@pytest.mark.parametrize('kind', ['static','xsuaa'])
@pytest.mark.parametrize('path', ['/v1/audio/transcriptions','/v1/transcriptions','/v1/transcribe'])
def test_both_tokens_http(cloud_client, kind, path):
    import io
    import wave
    client, jwt_token = cloud_client
    headers = {'Authorization':'Bearer ' + STATIC_TOKEN if kind == 'static' else jwt_token(), 'Origin':'https://unit.example'}
    audio = io.BytesIO()
    with wave.open(audio, 'wb') as f:
        f.setnchannels(1); f.setsampwidth(2); f.setframerate(16000); f.writeframes(b'\0' * 32000)
    payload = {'content':audio.getvalue()} if path == '/v1/transcribe' else {'files':{'file':('test.wav',audio.getvalue())}}
    assert client.post(path, headers=headers, **payload).status_code == 200
    assert client.post(path, **payload).status_code == 401
    assert client.post(path, headers={'Authorization':'Bearer incorrect'}, **payload).status_code == 401
    assert client.post(path, headers=dict(headers, Origin='https://evil.example'), **payload).status_code == 403


@pytest.mark.parametrize('kind', ['static','xsuaa','missing','invalid'])
def test_both_tokens_websocket(cloud_client, kind):
    client, jwt_token = cloud_client
    value = {'static':STATIC_TOKEN,'xsuaa':jwt_token().split(' ',1)[1],'missing':'','invalid':'incorrect'}[kind]
    with client.websocket_connect('/v1/stream', headers={'Origin':'https://unit.example'}) as ws:
        ws.send_json({'type':'start','sample_rate':16000,'format':'pcm_s16le','token':value})
        message = ws.receive_json()
        if kind in ('missing','invalid'):
            assert message['type'] == 'error'
        else:
            assert message['type'] == 'ready'
            ws.send_bytes(b'\0' * 3200)
            assert ws.receive_json()['type'] == 'ack'
            ws.send_json({'type':'stop'})
            assert ws.receive_json()['type'] == 'segment'
            assert ws.receive_json()['type'] == 'done'


def test_environment_key_is_uppercase(monkeypatch):
    # Simulate CF/Linux case-sensitive lookup, including when tests run on Windows.
    values = {'ACCESS_TOKEN': STATIC_TOKEN, 'access_token': 'legacy-test-only-' + 'b' * 32}
    monkeypatch.setattr('app.settings.os.getenv', lambda key, default=None: values.get(key, default))
    assert Settings().access_token == STATIC_TOKEN
    del values['ACCESS_TOKEN']
    assert Settings().access_token == ''
