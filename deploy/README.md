# Deploying StockBot on the shared Hetzner server

StockBot runs as one container next to TalentFlow on the same server (Hetzner CX23, Ubuntu 26.04, Docker). TalentFlow's Caddy container already owns ports 80/443 and handles HTTPS. StockBot joins TalentFlow's Docker network, publishes no ports, and gets its own hostname:

**https://stockbot.178.105.95.25.sslip.io**

```
Internet ──443──▶ Caddy (talentflow-caddy-1) ──┬──▶ api:8000      (TalentFlow)
                                               └──▶ stockbot:8000 (this app)
                       Docker network: talentflow_default
```

Resource use: about 400–700 MB RAM at runtime, capped at 1.2 GB. The image is about 1.5 GB and the data volume holds roughly 100–300 MB.

---

## 1. One-time: let Caddy load extra site files (TalentFlow repo)

TalentFlow's `Caddyfile` lives in its git repo, and its deploy runs `git reset --hard`, so editing the file directly on the server would be wiped. Make this change **in the TalentFlow repo** instead:

1. In `deploy/Caddyfile`, append this line at the end, outside any site block:
   ```
   import /etc/caddy/sites/*.caddy
   ```
2. In `compose.prod.yaml`, under the `caddy` service, add this to `volumes:`:
   ```yaml
   - /opt/caddy-sites:/etc/caddy/sites:ro
   ```
3. On the server:
   ```bash
   sudo mkdir -p /opt/caddy-sites
   ```
4. Commit and push, then redeploy TalentFlow as usual. Caddy is recreated once, so expect a few seconds of downtime.

> A Caddy `import` with a glob that matches no files is fine, so this is safe to deploy before StockBot exists.

## 2. Get the code and configure secrets

```bash
sudo git clone https://github.com/abdullahasif07/Stock-Bot.git /opt/stockbot
sudo chown -R $USER /opt/stockbot
cd /opt/stockbot
cp .env.example .env
nano .env
```

Set at least the following in `.env`:

```
GEMINI_API_KEY=...
ALPHA_VANTAGE_API_KEY=...
SEC_USER_AGENT="StockBot-Demo/2.0 your-real-email@example.com"   # required: SEC returns 403 otherwise
```

Optionally also set `DEMO_ACCESS_CODE=...` to gate the demo behind a code. `chmod 600 .env` keeps the file private.

## 3. Start the container

There are two ways to get the image.

**Option A: build on GitHub (recommended for this 2-vCPU box).** `.github/workflows/ci.yml` builds and pushes `ghcr.io/abdullahasif07/stock-bot:latest` on every push to `main`, after the tests pass.
- After the first run, go to GitHub → your profile → Packages → `stock-bot` → Package settings → change visibility to **Public**. Otherwise, run `docker login ghcr.io` on the server with a token that has `read:packages`.
- Then on the server:
  ```bash
  docker compose -f deploy/compose.prod.yaml pull
  docker compose -f deploy/compose.prod.yaml up -d
  ```

**Option B: build on the server.** This is simpler, but it uses both CPUs for about 5–10 minutes, which slows TalentFlow while it runs:
```bash
docker compose -f deploy/compose.prod.yaml up -d --build
```

Check it's healthy. The first boot loads the embedding model, so give it about 30 seconds:
```bash
docker compose -f deploy/compose.prod.yaml ps
docker compose -f deploy/compose.prod.yaml logs -f --tail=50
docker exec talentflow-caddy-1 wget -qO- http://stockbot:8000/api/health   # → {"status":"ok"}
```

## 4. Add the Caddy site

```bash
sudo cp deploy/stockbot.caddy /opt/caddy-sites/stockbot.caddy
docker exec talentflow-caddy-1 caddy reload --config /etc/caddy/Caddyfile
```

The reload has no downtime. Caddy fetches the TLS certificate automatically, then **https://stockbot.178.105.95.25.sslip.io** is live. You don't need any firewall changes.

---

## Updating

### Automatic (GitHub Actions)

Every push to `main` runs the tests, publishes the image if they pass, then SSHes into the server and runs `git pull`, `docker compose pull` and `docker compose up -d --wait`. The deploy job is skipped until these **repository secrets** exist (GitHub → Settings → Secrets and variables → Actions):

| Secret | Value |
|---|---|
| `DEPLOY_HOST` | the server's IP, e.g. `178.105.95.25` |
| `DEPLOY_USER` | the Linux user that owns `/opt/stockbot` and can run `docker` |
| `DEPLOY_SSH_KEY` | a private key whose public half is in that user's `~/.ssh/authorized_keys` |

Create a dedicated key for this, on your laptop:

```bash
ssh-keygen -t ed25519 -f stockbot_deploy -N "" -C "github-actions-stockbot"
ssh-copy-id -i stockbot_deploy.pub <user>@178.105.95.25
cat stockbot_deploy        # paste this into the DEPLOY_SSH_KEY secret, then delete both files
```

The GHCR package must be public, or the server must be logged in to `ghcr.io` (see step 3).

### Manual

```bash
cd /opt/stockbot
git pull
# Option A (GitHub-built image):
docker compose -f deploy/compose.prod.yaml pull && docker compose -f deploy/compose.prod.yaml up -d
# Option B (build on the server):
docker compose -f deploy/compose.prod.yaml up -d --build
```

The data volume survives updates and keeps caches, indexes and the daily usage counters.

## Useful commands

| Task | Command |
|---|---|
| Logs | `docker compose -f deploy/compose.prod.yaml logs -f` |
| Restart | `docker compose -f deploy/compose.prod.yaml restart` |
| Memory use | `docker stats --no-stream` |
| Remaining daily budgets | `curl -s https://stockbot.178.105.95.25.sslip.io/api/status` |
| Stop | `docker compose -f deploy/compose.prod.yaml down` (add `-v` only if you want to wipe cached data) |

## Using a real domain later

1. Add a DNS A record: `stockbot.yourdomain.com → 178.105.95.25`.
2. Change the hostname in `/opt/caddy-sites/stockbot.caddy`.
3. Reload Caddy (same command as in step 4).

## Troubleshooting

- **502 from Caddy:** the container isn't running or isn't on `talentflow_default`. Check `docker network inspect talentflow_default | grep stockbot`.
- **Answers appear all at once instead of streaming:** make sure the site block has `flush_interval -1` and no `encode`.
- **"Couldn't retrieve an annual report":** check `SEC_USER_AGENT` has a real contact email, then look at the logs for `[SEC]`.
- **TalentFlow's Caddy was recreated and StockBot is gone:** check the `import` line and the `/opt/caddy-sites` mount are still in TalentFlow's config (step 1).
