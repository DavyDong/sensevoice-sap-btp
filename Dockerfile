FROM python:3.11.15-slim-bookworm
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 \
    HOST=0.0.0.0 AUTH_MODE=xsuaa MODEL_ROOT=/app/models \
    HF_HUB_OFFLINE=1 HF_HUB_DISABLE_TELEMETRY=1 TORCH_THREADS=2
RUN apt-get update && apt-get install -y --no-install-recommends libsndfile1 libgomp1 \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 asr
WORKDIR /app
COPY requirements-linux.lock ./
RUN pip install --no-cache-dir --extra-index-url https://download.pytorch.org/whl/cpu -r requirements-linux.lock \
    && pip check
COPY --chown=asr:asr app ./app
COPY --chown=asr:asr scripts/download_models.py ./scripts/download_models.py
COPY --chown=asr:asr models.lock.json run.py ./
COPY --chown=asr:asr models ./models
COPY --chown=asr:asr licenses ./licenses
COPY --chown=asr:asr LICENSE THIRD_PARTY_NOTICES.md ./
RUN python scripts/download_models.py --verify && mkdir -p /app/.cache && chown asr:asr /app/.cache
USER asr
EXPOSE 8080
CMD ["python", "run.py"]
