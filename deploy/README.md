# Deploying Invoflow

One EU server running Docker Compose. Receipt files and nightly database backups go to Cloudflare R2. Every green CI run on `main` deploys automatically.

```
Caddy (HTTPS) ─┬─ /api, /health → api  (FastAPI + Tesseract + QR, migrations on start)
               └─ everything else → web (Next.js standalone)
api ── db (Postgres 16, local volume, not published)
api ── R2 bucket: invoflow-documents   (originals, versioning on)
backup ── R2 bucket: invoflow-backups  (pg_dump daily, 30 days kept)
```

Files here:

| File | What it is |
|---|---|
| `docker-compose.prod.yml` | The production stack. |
| `Caddyfile` | HTTPS, routing and security headers. |
| `.env.example` | Every setting the server needs. Copy it to `/opt/invoflow/.env` on the server. |
| `backup/` | Daily `pg_dump` to R2 (`backup.sh`) and the restore script (`restore.sh`). |
| `server-setup.sh` | One-time hardening of a fresh Ubuntu 24.04 server. |
| `rehearsal/` | The whole stack on your laptop, with no accounts: `./rehearsal/rehearse.sh`. |

## Accounts and who creates them

Gildo creates the accounts, because they need payment or identity. Claude never handles the real keys.

1. **Server:** Hetzner Cloud CX22 or similar, Ubuntu 24.04, in an EU location (Germany or Finland). Add your own SSH key when you create it.
2. **Domain:** point it at Cloudflare DNS. Add an `A` record for the domain (and `AAAA` if the server has IPv6) to the server's IP, with **DNS only** (grey cloud), so Caddy can get its certificate.
3. **Cloudflare R2:**
   - Create buckets `invoflow-documents` and `invoflow-backups`.
   - Turn on **object versioning** for `invoflow-documents`.
   - Create an R2 API token with Object Read & Write on both buckets.
   - Under CORS on `invoflow-documents`, allow `PUT` and `GET` from `https://<your domain>`. Browsers upload straight to R2.
4. **Clerk:** create a production instance for the domain. You need the publishable key (`pk_live_…`), the secret key (`sk_live_…`) and the Frontend API host.
5. **Sentry (optional):** create a free Python project and copy its DSN.

## First deploy

1. Make a deploy key on your laptop, without a passphrase:

   ```bash
   ssh-keygen -t ed25519 -f invoflow_deploy -N "" -C deploy@github
   ```

2. Harden the server:

   ```bash
   ssh root@SERVER_IP 'sh -s' < deploy/server-setup.sh "$(cat invoflow_deploy.pub)"
   ```

3. Create the production settings on the server. Fill in the values from `.env.example`, using a long random `POSTGRES_PASSWORD` (`openssl rand -base64 32`):

   ```bash
   ssh -i invoflow_deploy deploy@SERVER_IP 'cat > /opt/invoflow/.env && chmod 600 /opt/invoflow/.env' < my-prod.env
   ```

4. In GitHub (repo → Settings), add:
   - **Secrets:** `DEPLOY_HOST` (the server IP), `DEPLOY_USER` = `deploy`, and `DEPLOY_SSH_KEY` (the contents of the private key `invoflow_deploy`).
   - **Variable:** `CLERK_PUBLISHABLE_KEY` = `pk_live_…`. The publishable key is built into the browser bundle, so it is meant to be public.
   - **Environment:** create one named `production`. You can make it require your approval before every deploy.
5. Run **Actions → Deploy → Run workflow**, or merge anything to `main`. The workflow builds both images and pushes them to GHCR. It then copies the stack files to `/opt/invoflow`, pulls the images and starts everything. The API runs `alembic upgrade head` before serving, and the workflow waits for `https://DOMAIN/health`.

Delete `invoflow_deploy` and `my-prod.env` from your laptop once they're stored in GitHub and on the server.

## Day to day

Run these on the server, in `/opt/invoflow`:

```bash
alias dc='docker compose -f docker-compose.prod.yml --env-file .env'
```

| Task | Command |
|---|---|
| Status | `dc ps` |
| Logs | `dc logs -f api` (or `web`, `caddy`, `backup`) |
| Backup now | `dc exec backup backup.sh` |
| List backups | `dc exec backup restore.sh` |
| Restore (replaces the data) | `dc exec backup restore.sh invoflow-YYYYmmdd-HHMMSS.dump --yes` |
| Roll back the app | `sed -i 's/^IMAGE_TAG=.*/IMAGE_TAG=<older sha>/' .env && dc up -d` |

**Practise a restore once a month** on the rehearsal stack or a scratch server. A backup you have never restored doesn't count.

## Moving from Neon or another existing database

Is the existing database a Postgres that `create_all` built, rather than migrations? Then mark it as current once with `alembic stamp head`, instead of upgrading it. For a fresh database, nothing is needed: the API migrates it on start.

## Cost and limits (check the current prices before paying)

| Item | Cost |
|---|---|
| Server | about €4–6 a month |
| R2 | free up to 10 GB |
| Clerk, Cloudflare DNS, Sentry, GHCR | free tiers |

One server is a single point of failure, which is acceptable before revenue as long as backups are restored for practice. The upgrade order, once there are paying customers:

1. Managed Postgres.
2. A second app server behind a load balancer.
3. A job queue for OCR.

OCR runs in the API process, which is why there is one worker.
