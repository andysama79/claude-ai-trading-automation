# ── Base image ──────────────────────────────────────────────────────────────
# python:3.12-slim = Debian bookworm with only Python installed (~50 MB).
# Avoids the full python:3.12 image (~900 MB) which bundles GCC, headers, etc.
FROM python:3.12-slim

# ── System deps ─────────────────────────────────────────────────────────────
# kiteconnect needs libssl; slim image has it, but some yfinance deps need curl.
# --no-install-recommends keeps the layer small.
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
    && rm -rf /var/lib/apt/lists/*

# ── Non-root user ───────────────────────────────────────────────────────────
# Containers run as root by default — bad practice (if the process is
# compromised, attacker gets root on the container filesystem).
# We create a dedicated user and switch to it before running the app.
RUN useradd -m -u 1000 trader

WORKDIR /app

# ── Python deps ─────────────────────────────────────────────────────────────
# Copy requirements first (separate layer). Docker caches layers; if only
# source code changes, pip install layer is reused — much faster rebuilds.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── App source ──────────────────────────────────────────────────────────────
# Copy everything else. .dockerignore controls what's excluded.
COPY --chown=trader:trader . .

# ── Persistent state directories ────────────────────────────────────────────
# logs/ and the Kite session file must survive container restarts.
# We declare them as VOLUMEs — Docker treats these as mount points.
# In production, docker-compose or Fly.io will mount real host paths here.
RUN mkdir -p logs && chown trader:trader logs

USER trader

# ── Runtime ─────────────────────────────────────────────────────────────────
# Default command. Override with --config if your yaml lives elsewhere.
# Secrets come from env vars (see .env.example) — never baked into image.
CMD ["python", "-m", "trader", "--config", "config.yaml"]
