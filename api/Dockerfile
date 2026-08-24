# syntax=docker/dockerfile:1

# ---- builder -----------------------------------------------------------------
# Dependencies are installed into their own layer so application edits do not
# invalidate the pip cache on every rebuild.
FROM python:3.12-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt


# ---- runtime -----------------------------------------------------------------
FROM python:3.12-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH" \
    # Inside compose, MongoDB and MinIO are reachable by service name.
    MONGODB_URL=mongodb://root:rootpassword@mongodb:27017 \
    MINIO_ENDPOINT=minio:9000 \
    LOCAL_ASSET_DIR=/data/assets

COPY --from=builder /opt/venv /opt/venv

# Non-root: the container writes only to /data, which is a named volume.
RUN useradd --create-home --uid 10001 decalove \
    && mkdir -p /data/assets \
    && chown -R decalove:decalove /data

WORKDIR /srv/api
COPY --chown=decalove:decalove app ./app

USER decalove
EXPOSE 8000

# The API boots even when MongoDB and MinIO are unreachable, so the healthcheck
# asks a real question -- is the runtime assembled? -- not just "is the port open".
HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=5 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4).status == 200 else 1)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
