import io
import json

import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient

from app.audio import decode_audio
from app.main import create_app
from app.settings import Settings
from app.streaming import SegmentBuffer


class FakeStream:
    def feed(self, data, final=False):
        return [{'type': 'segment', 'text': 'test', 'final': True}] if final else []


class FakeEngine:
    def __init__(self, settings):
        pass

    def transcribe(self, samples, language):
        return {'text': 'test', 'audio_seconds': len(samples) / 16000, 'language': language}

    def new_stream(self, language):
        return FakeStream()


@pytest.fixture
def client(monkeypatch):
    monkeypatch.delenv('VCAP_APPLICATION', raising=False)
    with TestClient(create_app(Settings(auth_mode='none', host='127.0.0.1', max_bytes=100000), FakeEngine), base_url='http://127.0.0.1:8000') as c:
        yield c


def wav(rate=16000, channels=1):
    buffer = io.BytesIO()
    sf.write(buffer, np.zeros((rate, channels)), rate, format='WAV')
    return buffer.getvalue()


@pytest.mark.parametrize('path', ['/v1/audio/transcriptions', '/v1/transcriptions'])
def test_file_and_raw(client, path):
    assert client.get('/health/ready').status_code == 200
    response = client.post(path, files={'file': ('a.wav', wav())}, data={'language': 'auto'})
    assert response.status_code == 200 and response.json()['audio_seconds'] == 1
    assert client.post('/v1/transcribe', content=wav()).status_code == 200


def test_bad_inputs(client):
    assert client.post('/v1/transcribe', content=b'invalid').status_code == 400
    assert client.post('/v1/transcribe?language=xx', content=wav()).status_code == 422
    assert client.post('/v1/transcribe', content=b'0' * 100001).status_code == 413


@pytest.mark.parametrize('path', ['/v1/audio/transcriptions', '/v1/transcriptions'])
def test_multipart_contract(client, path):
    assert client.post(path, files={'file': ('a.wav', b'0' * 100001)}).status_code == 413
    assert client.post(path, files={'file': ('a.wav', b'invalid')}).status_code == 400
    assert client.post(path, files={'file': ('a.wav', wav())}, data={'language': 'xx'}).status_code == 422
    assert client.post(path, data={'language': 'auto'}).status_code == 422
    assert client.post(path, files={'file': ('a.wav', wav())}, headers={'origin':'https://evil.example'}).status_code == 403


def test_openapi_canonical_path(client):
    paths = client.get('/openapi.json').json()['paths']
    assert '/v1/audio/transcriptions' in paths
    assert '/v1/transcriptions' not in paths


def test_decode_limits_and_resampling():
    assert len(decode_audio(wav(44100, 2))) == 16000
    with pytest.raises(ValueError):
        decode_audio(wav(16000, 3))
    with pytest.raises(ValueError):
        decode_audio(wav(), max_seconds=0)


def start(ws):
    ws.send_json({'type': 'start', 'format': 'pcm_s16le', 'sample_rate': 16000})
    assert ws.receive_json()['type'] == 'ready'


def test_websocket_flush_and_busy(client):
    with client.websocket_connect('ws://127.0.0.1:8000/v1/stream') as ws:
        start(ws)
        assert client.post('/v1/transcribe', content=wav()).status_code == 429
        ws.send_bytes(b'\0' * 3200)
        assert ws.receive_json()['type'] == 'ack'
        ws.send_json({'type': 'stop'})
        assert ws.receive_json()['type'] == 'segment'
        assert ws.receive_json()['type'] == 'done'
    assert client.post('/v1/transcribe', content=wav()).status_code == 200


@pytest.mark.parametrize('frame', [b'\0', b'\0' * 3202])
def test_invalid_frames(client, frame):
    with client.websocket_connect('ws://127.0.0.1:8000/v1/stream') as ws:
        start(ws)
        ws.send_bytes(frame)
        assert ws.receive_json()['type'] == 'error'


def test_wrong_origin(client):
    from starlette.websockets import WebSocketDisconnect
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect('ws://127.0.0.1:8000/v1/stream', headers={'origin': 'https://evil.example'}):
            pass


def test_local_host_and_http_origin(client):
    assert client.get('/', headers={'host': 'evil.example:8000'}).status_code == 403
    assert client.post('/v1/transcribe', content=wav(), headers={'origin':'https://evil.example'}).status_code == 403


def test_cloud_fail_closed(monkeypatch):
    monkeypatch.setenv('VCAP_APPLICATION', '{}')
    with pytest.raises(ValueError):
        create_app(Settings(auth_mode='none'), FakeEngine)
    monkeypatch.setenv('VCAP_SERVICES', '{}')
    with pytest.raises(ValueError):
        create_app(Settings(auth_mode='xsuaa'), FakeEngine)


def test_segment_boundaries_and_memory():
    buffer = SegmentBuffer(max_segment_ms=1000)
    buffer.append(np.arange(16000, dtype=np.float32))
    first = buffer.boundaries([[0, -1]])
    assert [(x[0], x[1]) for x in first] == [(0, 1000)]
    buffer.append(np.ones(8000, dtype=np.float32))
    last = buffer.boundaries([[-1, 1500]])
    assert [(x[0], x[1]) for x in last] == [(1000, 1500)]
    for _ in range(100):
        buffer.append(np.zeros(1600, dtype=np.float32))
        assert not buffer.boundaries([])
    assert len(buffer.data) <= 32000


def test_final_partial_segment():
    buffer = SegmentBuffer()
    buffer.append(np.zeros(8000, dtype=np.float32))
    buffer.boundaries([[100, -1]])
    final = buffer.boundaries([], final=True)
    assert [(x[0], x[1]) for x in final] == [(100, 500)]
    assert not buffer.boundaries([], final=True)
