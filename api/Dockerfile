# syntax=docker/dockerfile:1

# Using official PyTorch image with CUDA support pre-installed
# so PyTorch/CUDA wheels are not downloaded on every build.
FROM pytorch/pytorch:latest

# Only what describes *this image's* filesystem layout -- the paths the RUN below
# creates and the volumes mount over. Everything else the app reads is a setting, and
# settings live in app/config.py with .env as the single place to override them; baking
# them in here would silently shadow both. Service addresses in particular describe a
# compose network the image knows nothing about, so docker-compose.yml sets those.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DEBIAN_FRONTEND=noninteractive \
    LOCAL_ASSET_DIR=/data/assets \
    # SDXL weights are stored under /srv/api/models/sdxl (a mounted volume).
    # Point HF_HOME there so diffusers never writes to ~/.cache.
    SDXL_MODEL_DIR=/srv/api/models/sdxl \
    HF_HOME=/srv/api/models/sdxl \
    TRANSFORMERS_CACHE=/srv/api/models/sdxl

WORKDIR /build

COPY requirements.txt ./
# Install additional project dependencies (torch is already pre-installed in base image)
RUN pip install --no-cache-dir -r requirements.txt

# Non-root: the container writes to /data and /srv/api/models.
RUN useradd --create-home --uid 10001 decalove \
    && mkdir -p /data/assets /srv/api/models/sdxl \
    && chown -R decalove:decalove /data /srv/api/models

WORKDIR /srv/api
COPY --chown=decalove:decalove app ./app
COPY --chown=decalove:decalove download_model.py ./download_model.py
COPY --chown=decalove:decalove scripts ./scripts

USER decalove
EXPOSE 8000

# The API boots even when MongoDB and MinIO are unreachable, so the healthcheck
# asks a real question -- is the runtime assembled? -- not just "is the port open".
HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=5 \
    CMD python3 -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4).status == 200 else 1)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
