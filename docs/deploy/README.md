# Deployment Guide

## Local Docker (test before deploying)

```bash
# 1. Copy example files
cp config.example.yaml config.yaml
cp .env.example .env
# Edit both files with your real values

# 2. Create empty Kite session file (mounted as volume)
touch kite_session

# 3. Build image
docker compose build

# 4. Auth (manual mode): get your access token from Kite and write it
echo "YOUR_ACCESS_TOKEN" > kite_session

# 5. Run
docker compose up -d

# Tail logs
docker compose logs -f
```

---

## Option A: Fly.io (Recommended — ~$2/month)

Fly.io runs persistent VMs (not serverless). Your bot stays alive 24/7.

### Why Fly.io?

- Persistent process (unlike Cloud Run which sleeps on idle)
- `fly deploy` in one command
- Secrets management built-in (no `.env` file on server)
- Free allowance covers 3 shared-CPU VMs with 256 MB RAM

### Setup

```bash
# Install Fly CLI
curl -L https://fly.io/install.sh | sh

# Login
fly auth login

# Initialize app (run once, from project root)
fly launch --no-deploy --name trader-YOUR_NAME

# This creates fly.toml — commit it (no secrets inside)
```

### Secrets

```bash
# Set secrets (replaces .env file on Fly)
fly secrets set \
  KITE_API_KEY="your_key" \
  KITE_API_SECRET="your_secret" \
  KITE_TOTP_SECRET="your_totp_base32" \
  TG_API_ID="12345" \
  TG_API_HASH="your_hash" \
  TG_BOT_TOKEN="your_bot_token"
```

Secrets are encrypted at rest. Never in your repo.

### Persistent volume (Kite session + trade log)

```bash
# Create a 1 GB volume in the region closest to you
fly volumes create trader_data --size 1 --region sin  # sin = Singapore, bom = Mumbai
```

Add to `fly.toml`:

```toml
[mounts]
  source = "trader_data"
  destination = "/app/data"
```

Update `config.yaml` to write logs to `/app/data/logs/trades.jsonl` and
point Kite session to `/app/data/.kite_session`.

### Deploy

```bash
fly deploy
fly status   # check it's running
fly logs     # tail live logs
```

### Kite auth on Fly

- **TOTP mode (recommended):** set `KITE_TOTP_SECRET` secret → fully automated daily re-auth
- **Manual mode:** SSH into machine and write token: `fly ssh console` → `echo "TOKEN" > /app/data/.kite_session`

---

## Option B: GCP Compute Engine (Free tier)

GCP gives one `e2-micro` VM free forever per account. Good if you already use GCP.

### Setup

```bash
# Create VM (free tier: us-central1, us-east1, or us-west1 only)
gcloud compute instances create trader \
  --machine-type=e2-micro \
  --zone=us-central1-a \
  --image-family=debian-12 \
  --image-project=debian-cloud \
  --boot-disk-size=20GB

# SSH in
gcloud compute ssh trader
```

### On the VM

```bash
# Install Docker
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
# log out and back in

# Clone repo
git clone https://github.com/YOUR/repo.git
cd claude-ai-trading-automation

# Set up config and env
cp config.example.yaml config.yaml
nano config.yaml
nano .env          # add secrets

# Run
docker compose up -d
docker compose logs -f
```

### Auto-start on reboot

```bash
# docker compose already has restart: unless-stopped
# VM needs to auto-start Docker on boot (it does by default on Debian)
sudo systemctl enable docker
```

---

## Option C: AWS Lightsail (~$3.50/month)

Simplest AWS option. Fixed monthly price, includes bandwidth.

```bash
# Create instance: Amazon Linux 2023, nano ($3.50/mo) or micro ($5/mo)
# Via console: https://lightsail.aws.amazon.com

# SSH in via Lightsail console or download key pair

# Install Docker (Amazon Linux)
sudo yum update -y
sudo yum install docker -y
sudo service docker start
sudo usermod -aG docker ec2-user

# Same as GCP from here: git clone, docker compose up -d
```

---

## Choosing the right option

| Need | Use |
|------|-----|
| Cheapest possible + simple deploy | Fly.io |
| Already on GCP / want free tier | GCP e2-micro |
| Want AWS ecosystem | Lightsail |
| Already have a VPS (DigitalOcean, Hetzner, etc.) | Docker Compose directly |

**For Mumbai market hours:** deploy in `ap-south-1` (AWS Mumbai) or `bom` (Fly Mumbai) or `asia-south1` (GCP Mumbai) to minimize LTP poll latency.

---

## Monitoring

```bash
# Fly.io
fly logs
fly status

# GCP / Lightsail / VPS
docker compose logs -f
docker stats trader   # live CPU/memory
```

## Updating the bot

```bash
# On Fly.io (from local machine)
git pull && fly deploy

# On VPS
git pull && docker compose up -d --build
```
