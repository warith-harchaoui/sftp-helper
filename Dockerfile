# syntax=docker/dockerfile:1.6
#
# sftp-helper — reproducible container image.
#
# Two-stage build: the base stage pulls the system deps needed for
# paramiko / cryptography (no compiler — everything installs from wheels)
# and installs the package with the [api,mcp] extras so the container
# can serve the HTTP + MCP surfaces out of the box.
#
# The container reads credentials from either:
#   - the file mounted at $SFTP_HELPER_CONFIG (bind-mount at runtime), or
#   - the env vars SFTP_HOST / SFTP_LOGIN / SFTP_PASSWD /
#     SFTP_DESTINATION_PATH / SFTP_HTTPS.
#
# Build:
#   docker build -t sftp-helper .
#
# Run (HTTP + MCP on 0.0.0.0:8000, credentials via env):
#   docker run --rm -p 8000:8000 \
#     -e SFTP_HOST=sftp.example.com \
#     -e SFTP_LOGIN=alice \
#     -e SFTP_PASSWD=secret \
#     -e SFTP_DESTINATION_PATH=/var/www/uploads \
#     -e SFTP_HTTPS=https://example.com/uploads \
#     sftp-helper
#
# Run (credentials via mounted JSON file):
#   docker run --rm -p 8000:8000 \
#     -v $PWD/sftp_config.json:/app/sftp_config.json:ro \
#     -e SFTP_HELPER_CONFIG=/app/sftp_config.json \
#     sftp-helper
#
# Run CLI one-shot:
#   docker run --rm -v $PWD:/data \
#     -e SFTP_HELPER_CONFIG=/data/sftp_config.json \
#     sftp-helper \
#     sftp-helper upload --input /data/local.txt --remote /uploads/local.txt

# --- base -------------------------------------------------------------------
FROM python:3.11-slim AS base

# System deps: tini for signal handling, plus the SSL / crypto libs
# paramiko wheels dynamically link against on slim images.
RUN apt-get update && apt-get install --no-install-recommends -y \
        tini \
        libssl3 \
        openssh-client \
    && rm -rf /var/lib/apt/lists/*

# Non-root runtime user; the app never needs root at runtime.
RUN useradd --create-home --shell /bin/bash app
WORKDIR /app

# --- deps -------------------------------------------------------------------
# Copy the package first so pip picks up pyproject.toml before we invalidate
# the layer with source changes.
COPY --chown=app:app pyproject.toml README.md LICENSE ./
COPY --chown=app:app sftp_helper ./sftp_helper

RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir '.[api,mcp]'

# --- runtime ----------------------------------------------------------------
USER app
EXPOSE 8000
ENV PYTHONUNBUFFERED=1 \
    SFTP_HELPER_HOST=0.0.0.0 \
    SFTP_HELPER_PORT=8000

# tini reaps orphan children (paramiko subprocesses) cleanly on SIGTERM.
ENTRYPOINT ["/usr/bin/tini", "--"]
# Default: serve FastAPI + MCP. Override for one-shot CLI usage.
CMD ["sftp-helper-mcp"]
