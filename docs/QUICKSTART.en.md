# SenseVoice on SAP BTP — quick start

CPU speech recognition with FunASR, SenseVoiceSmall, FSMN-VAD and FastAPI. Includes a browser UI, file APIs, segmented microphone transcription over WebSocket, XSUAA OAuth2 and an optional shared `ACCESS_TOKEN`.

Windows local execution and an actual SAP BTP Cloud Foundry **Python buildpack** deployment were validated on 2026-10-15. This is an independent community integration; it does not provide a hosted public inference endpoint. Model weights and account credentials are not included.

## Local setup

Install Git and [uv](https://docs.astral.sh/uv/getting-started/installation/), then:

```bash
git clone https://github.com/DavyDong/sensevoice-sap-btp.git
cd sensevoice-sap-btp
```

Windows PowerShell:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/setup.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/start.ps1
```

macOS/Linux:

```bash
bash scripts/setup.sh
bash scripts/start.sh
```

Visit http://127.0.0.1:8000 and leave the token field empty. Anonymous mode is restricted to loopback. The scripts create a Python 3.11 environment and download pinned official models with checksum verification. Allow approximately 0.94 GB for model files plus dependencies/caches; the measured Windows process peak was about 3.12 GiB. macOS scripts have not been tested on a Mac.

## SAP BTP deployment

Follow the [deployment guide](DEPLOYMENT.md) for prerequisite checks and details. After local setup, target **your own** CF org/space and ensure XSUAA application, cflinuxfs5, the required Python buildpack runtime, 6G memory and 6G disk are available.

```powershell
Copy-Item deployment.vars.example.yml deployment.vars.yml
Copy-Item xs-security.json xs-security.local.json
```

Edit `deployment.vars.yml`: use a unique route from your CF domain and choose app/service names belonging to this project. Edit `xs-security.local.json`: set a unique `xsappname`. Then, assuming the default app/service names:

```powershell
cf create-service xsuaa application sensevoice-xsuaa -c xs-security.local.json
# Wait for successful service creation, then:
.\.venv\Scripts\python.exe scripts/package_cf.py --stage-models dist/sensevoice-cf.zip
cf push -f manifest-buildpack.yml --vars-file deployment.vars.yml -p dist/sensevoice-cf.zip
```

Staging downloads the pinned models into the droplet; application startup verifies and loads them offline. Without `--stage-models`, the packager includes the locally downloaded weights. Dependencies still need their package registries. The app uses CF's `PORT` and a single worker. Docker files are provided as an alternative but have not been built/validated.

## Authentication and API

Obtain an XSUAA client-credentials token using the binding's URL, client ID and secret, or use the Windows helper against your currently selected CF space:

```powershell
$token = & .\scripts\copy_cloud_token.ps1 -App sensevoice-asr -ServiceName sensevoice-xsuaa -PassThru
curl.exe -H "Authorization: Bearer $token" -F "file=@sample.wav" -F "language=auto" https://YOUR_ROUTE/v1/audio/transcriptions
```

An optional uppercase `ACCESS_TOKEN` can be set in BTP User-Provided Variables. Use a random 32–256 character ASCII Bearer token; restart after changes. Empty disables it. XSUAA remains required and continues to work. This shared token does not expire automatically, identify users, or make a public route internal-only. Never commit actual secrets.

The UI accepts the token alone, without `Bearer`. `/v1/audio/transcriptions` uses multipart `file` and optional `language=auto/zh/en`; `/v1/transcribe` accepts raw audio. Supported files: WAV, FLAC, OGG, MP3; mono/stereo, 8–48 kHz, up to 120 seconds and a 20 MiB total request. One recognition session per instance; concurrent work receives 429.

WebSocket `/v1/stream` accepts a JSON start message followed by mono 16 kHz PCM16 frames, returning ACKs and completed segments. This is segmented recognition, not native token-by-token streaming. See [TOKEN-API.md](../TOKEN-API.md), Postman examples and the ABAP example.

## Validation and licensing

Run `python -m pytest -q` in the installed environment, then `node tests/test_worklet.cjs` and `node tests/test_transport.cjs`. `scripts/smoke_test.py` requires a running server and downloaded models for real HTTP/WS inference.

See [validation notes](VALIDATION.md). Natural bilingual speech accuracy, physical microphones, macOS, Docker and ABAP activation still require validation in your environment. The synthetic mixed sample is a concatenation of official recordings, not an accuracy benchmark.

Original integration code is [MIT-licensed](../LICENSE). Model weights and dependencies retain their own licenses; notably SenseVoiceSmall uses the separate FunASR model agreement. Read [third-party notices](../THIRD_PARTY_NOTICES.md) before using or redistributing model-containing artifacts.
