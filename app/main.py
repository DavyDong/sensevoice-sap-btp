import asyncio
import json
import logging
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .audio import decode_audio
from .auth import Auth
from .settings import Settings

LANGUAGES = {'auto', 'zh', 'en'}
logger = logging.getLogger('sensevoice')


class BodyLimit:
    def __init__(self, app, limit):
        self.app, self.limit = app, limit

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http' or scope['method'] not in ('POST', 'PUT', 'PATCH'):
            return await self.app(scope, receive, send)
        payload = bytearray()
        while True:
            message = await receive()
            if message['type'] == 'http.disconnect':
                return
            payload.extend(message.get('body', b''))
            if len(payload) > self.limit:
                return await JSONResponse({'detail': 'Upload exceeds request size limit'}, 413)(scope, receive, send)
            if not message.get('more_body', False):
                break
        delivered = False

        async def bounded_receive():
            nonlocal delivered
            if delivered:
                return await receive()
            delivered = True
            return {'type': 'http.request', 'body': bytes(payload), 'more_body': False}
        await self.app(scope, bounded_receive, send)


def create_app(settings=None, engine_factory=None):
    settings = settings or Settings()
    settings.validate()
    auth = Auth(settings)
    local_hosts = {f'127.0.0.1:{settings.port}', f'localhost:{settings.port}', f'[::1]:{settings.port}'}
    origins = set(settings.allowed_origins)
    if settings.auth_mode == 'none':
        origins.update('http://' + host for host in local_hosts)
    else:
        cloud_routes = json.loads(os.getenv('VCAP_APPLICATION', '{}')).get('application_uris', [])
        origins.update('https://' + route for route in cloud_routes)

    @asynccontextmanager
    async def lifespan(app):
        if engine_factory is None:
            from .engine import Engine
            factory = Engine
        else:
            factory = engine_factory
        app.state.ready = False
        app.state.busy = False
        app.state.engine = await asyncio.to_thread(factory, settings)
        app.state.ready = True
        yield
        app.state.ready = False

    app = FastAPI(title='SenseVoice local / BTP ASR', version='1.0.0', lifespan=lifespan,
                  docs_url='/docs' if settings.auth_mode == 'none' else None,
                  redoc_url=None, openapi_url='/openapi.json' if settings.auth_mode == 'none' else None)
    app.add_middleware(BodyLimit, limit=settings.max_bytes)

    @app.middleware('http')
    async def security(request, call_next):
        if settings.auth_mode == 'none' and request.headers.get('host') not in local_hosts:
            return JSONResponse({'detail': 'Local host required'}, 403)
        if request.method == 'POST' and request.headers.get('origin') and request.headers['origin'] not in origins:
            return JSONResponse({'detail': 'Origin not allowed'}, 403)
        if request.url.path.startswith('/v1/'):
            try:
                await asyncio.to_thread(auth.verify, request.headers.get('authorization', ''))
            except HTTPException as error:
                return JSONResponse({'detail': error.detail}, error.status_code, headers=error.headers)
        response = await call_next(request)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Cache-Control'] = 'no-store'
        response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; worker-src 'self'; frame-ancestors 'none'"
        return response

    @app.get('/health/live')
    def live():
        return {'status': 'alive'}

    @app.get('/health/ready')
    def ready():
        return JSONResponse({'ready': bool(getattr(app.state, 'ready', False))},
                            200 if getattr(app.state, 'ready', False) else 503)

    def acquire():
        if app.state.busy:
            raise HTTPException(429, 'One recognition session is already active', headers={'Retry-After': '5'})
        app.state.busy = True

    async def transcribe(payload, language):
        if language not in LANGUAGES:
            raise HTTPException(422, 'language must be auto, zh or en')
        acquire()
        try:
            samples = await asyncio.to_thread(decode_audio, payload, settings.max_audio_seconds)
            return await asyncio.to_thread(app.state.engine.transcribe, samples, language)
        except ValueError as error:
            raise HTTPException(400, str(error)) from error
        finally:
            app.state.busy = False

    @app.post('/v1/audio/transcriptions')
    @app.post('/v1/transcriptions', include_in_schema=False)
    async def multipart(file: UploadFile = File(...), language: str = Form('auto')):
        try:
            return await transcribe(await file.read(settings.max_bytes + 1), language)
        finally:
            await file.close()

    @app.post('/v1/transcribe')
    async def raw(request: Request, language: str = 'auto'):
        return await transcribe(await request.body(), language)

    @app.websocket('/v1/stream')
    async def stream(ws: WebSocket):
        # Browsers must be same origin, or explicitly allowlisted. Non-browser clients omit Origin.
        origin = ws.headers.get('origin')
        if settings.auth_mode == 'none' and ws.headers.get('host') not in local_hosts:
            return await ws.close(code=1008)
        if origin and origin not in origins:
            return await ws.close(code=1008)
        await ws.accept()
        owned = False
        try:
            first = await asyncio.wait_for(ws.receive_text(), 10)
            if len(first) > 18000:
                raise ValueError('Handshake too large')
            config = json.loads(first)
            if not isinstance(config, dict) or config.get('type') != 'start':
                raise ValueError('First message must be a start object')
            token = config.get('token', '')
            if not isinstance(token, str):
                raise ValueError('token must be a string')
            expiry = await asyncio.to_thread(auth.verify, ws.headers.get('authorization', '') or ('Bearer ' + token if token else ''))
            if config.get('sample_rate') != 16000 or config.get('format') != 'pcm_s16le':
                raise ValueError('Expected 16 kHz mono pcm_s16le')
            language = config.get('language', 'auto')
            if language not in LANGUAGES:
                raise ValueError('language must be auto, zh or en')
            acquire()
            owned = True
            session = app.state.engine.new_stream(language)
            started, total = time.monotonic(), 0
            await ws.send_json({'type': 'ready', 'frame_bytes': 3200, 'max_session_seconds': settings.max_session_seconds})
            while True:
                remaining = min(30, settings.max_session_seconds - (time.monotonic() - started), expiry - time.time())
                if remaining <= 0:
                    raise ValueError('Session or token expired')
                message = await asyncio.wait_for(ws.receive(), remaining)
                if message['type'] == 'websocket.disconnect':
                    break
                if message.get('bytes') is not None:
                    data = message['bytes']
                    if not data or len(data) > 3200 or len(data) % 2:
                        raise ValueError('Binary frames must contain 2–3200 bytes of PCM16')
                    total += len(data)
                    if total > settings.max_session_seconds * 32000:
                        raise ValueError('Audio duration limit exceeded')
                    results = await asyncio.to_thread(session.feed, data)
                    if time.time() >= expiry:
                        raise ValueError('Access token expired')
                    for item in results:
                        await ws.send_json(item)
                    await ws.send_json({'type': 'ack', 'audio_ms': total / 32})
                else:
                    control = message.get('text', '')
                    if len(control) > 256 or json.loads(control) != {'type': 'stop'}:
                        raise ValueError('Expected binary PCM or {"type":"stop"}')
                    results = await asyncio.to_thread(session.feed, b'', True)
                    if time.time() >= expiry:
                        raise ValueError('Access token expired')
                    for item in results:
                        await ws.send_json(item)
                    await ws.send_json({'type': 'done', 'audio_ms': total / 32})
                    await ws.close(code=1000)
                    break
        except WebSocketDisconnect:
            pass
        except (ValueError, TypeError, HTTPException, asyncio.TimeoutError) as error:
            try:
                await ws.send_json({'type': 'error', 'detail': error.detail if isinstance(error, HTTPException) else str(error) or 'Connection timed out'})
                await ws.close(code=1008)
            except (RuntimeError, WebSocketDisconnect):
                pass
        except Exception:
            logger.exception('WebSocket inference failed')
            try:
                await ws.close(code=1011, reason='Recognition failed')
            except (RuntimeError, WebSocketDisconnect):
                pass
        finally:
            if owned:
                app.state.busy = False

    static = Path(__file__).with_name('static')
    app.mount('/static', StaticFiles(directory=static), name='static')

    @app.get('/')
    def index():
        return FileResponse(static / 'index.html')

    return app
