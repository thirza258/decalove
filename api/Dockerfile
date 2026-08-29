# syntax=docker/dockerfile:1

# ---- builder -----------------------------------------------------------------
# Dependencies are installed into their own layer so application edits do not
# invalidate the pip cache on every rebuild.
# Using NVIDIA CUDA base image for GPU-accelerated SDXL inference.
FROM nvidia/cuda:12.9.0-runtime-ubuntu24.04 AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
        python3 python3-venv python3-pip \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt ./
# Install PyTorch with CUDA support from the PyTorch index.
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cu128 \
    && pip install --no-cache-dir -r requirements.txt


# ---- runtime -----------------------------------------------------------------
FROM nvidia/cuda:12.9.0-runtime-ubuntu24.04 AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DEBIAN_FRONTEND=noninteractive \
    PATH="/opt/venv/bin:$PATH" \
    # Inside compose, MongoDB and MinIO are reachable by service name.
    MONGODB_URL=mongodb://root:rootpassword@mongodb:27017 \
    MINIO_ENDPOINT=minio:9000 \
    LOCAL_ASSET_DIR=/data/assets \
    # SDXL weights are stored under /srv/api/models/sdxl (a mounted volume).
    # Point HF_HOME there so diffusers never writes to ~/.cache.
    HF_HOME=/srv/api/models/sdxl \
    TRANSFORMERS_CACHE=/srv/api/models/sdxl

RUN apt-get update && apt-get install -y --no-install-recommends \
        python3 python3-venv \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /opt/venv /opt/venv

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
