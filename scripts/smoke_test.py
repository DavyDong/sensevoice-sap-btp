"""Real HTTP + WebSocket audio replay. Requires a running server and downloaded models."""
import argparse
import asyncio
import io
import json
import os
import time
from pathlib import Path

import httpx
import numpy as np
import soundfile as sf
import websockets

ROOT = Path(__file__).resolve().parents[1]


def encode(samples):
    target = io.BytesIO()
    sf.write(target, samples, 16000, format='WAV', subtype='PCM_16')
    return target.getvalue()


async def stream(url, samples, token):
    frames = (np.clip(samples, -1, 1) * 32767).astype('<i2').tobytes()
    segments, first_result = [], None
    async with websockets.connect(url.replace('http', 'ws', 1) + '/v1/stream', max_size=1024*1024) as ws:
        await ws.send(json.dumps({'type':'start', 'format':'pcm_s16le', 'sample_rate':16000, 'language':'auto', 'token':token}))
        ready = json.loads(await ws.recv())
        assert ready['type'] == 'ready', ready
        start = time.perf_counter()
        slots = asyncio.Semaphore(8)

        async def send_audio():
            for offset in range(0, len(frames), 3200):
                await asyncio.sleep(max(0, start + offset / 32000 - time.perf_counter()))
                await asyncio.wait_for(slots.acquire(), 30)
                if time.perf_counter() - start - offset / 32000 > 2:
                    raise AssertionError('Audio transmission backlog exceeded 2 seconds')
                await ws.send(frames[offset:offset + 3200])
            for _ in range(8):
                await asyncio.wait_for(slots.acquire(), 60)
            await ws.send(json.dumps({'type':'stop'}))

        async def receive_results():
            nonlocal first_result
            while True:
                message = json.loads(await asyncio.wait_for(ws.recv(), 60))
                if message['type'] == 'ack':
                    slots.release()
                elif message['type'] == 'segment':
                    received = time.perf_counter() - start
                    first_result = first_result or received
                    message['received_seconds'] = round(received, 3)
                    message['after_segment_end_seconds'] = round(received - message['end_ms'] / 1000, 3)
                    segments.append(message)
                elif message['type'] == 'done':
                    return
                else:
                    raise AssertionError(message)

        async with asyncio.TaskGroup() as group:
            group.create_task(send_audio())
            group.create_task(receive_results())
    assert segments, 'No streaming text recognized'
    return {'segments':segments, 'wall_seconds':round(time.perf_counter()-start,3),
            'first_result_seconds':first_result, 'max_in_flight_frames':8}


def main():
    import sys
    sys.path.insert(0, str(ROOT))
    from app.audio import decode_audio
    parser = argparse.ArgumentParser()
    parser.add_argument('--url', default='http://127.0.0.1:8000')
    parser.add_argument('--report', type=Path, default=ROOT/'reports'/'real-smoke.json')
    args = parser.parse_args()
    token = os.getenv('ASR_ACCESS_TOKEN', '')
    headers = {'Authorization':'Bearer '+token} if token else {}
    samples = {lang:decode_audio((ROOT/'models'/'sensevoice'/'example'/f'{lang}.mp3').read_bytes()) for lang in ('zh','en')}
    # Synthetic code switching: concatenate official recordings. This is NOT natural bilingual speech validation.
    samples['mixed_synthetic'] = np.concatenate((samples['zh'], np.zeros(4800), samples['en']))
    report = {'test_type':'real model / HTTP + WS replay', 'url':args.url, 'file_endpoint':'/v1/audio/transcriptions', 'natural_mixed_speech_verified':False, 'physical_microphone_verified':False, 'files':{}}
    with httpx.Client(timeout=180, trust_env=False) as client:
        assert client.get(args.url+'/health/ready').status_code == 200
        for name, audio in samples.items():
            response = client.post(args.url+'/v1/audio/transcriptions', files={'file':(name+'.wav', encode(audio), 'audio/wav')}, data={'language':'auto'}, headers=headers)
            response.raise_for_status()
            report['files'][name] = response.json()
            assert response.json()['text'], f'Empty transcript: {name}'
            print(name, json.dumps(response.json(), ensure_ascii=False), flush=True)
        silent = client.post(args.url+'/v1/transcribe', content=encode(np.zeros(16000)), headers=headers)
        silent.raise_for_status()
        assert silent.json()['text'] == '', 'Silence hallucinated text'
        report['silence'] = 'passed'
    report['websocket'] = asyncio.run(stream(args.url, samples['mixed_synthetic'], token))
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), 'utf-8')
    print(f'Real integration report: {args.report}')


if __name__ == '__main__':
    main()
