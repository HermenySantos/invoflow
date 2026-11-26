# Deploying Invoflow

One EU server running Docker Compose. Receipt files and nightly database backups go to Cloudflare R2. Every green CI run on `main` builds and pushes images when the repository variable `CLERK_PUBLISHABLE_KEY` is set and, after trimming whitespace, starts with `pk_live_` (a live key is required; the check is case-sensitive), and deploys only when `DEPLOY_HOST` is set too. If the Clerk variable is unset, the images and deploy jobs are skipped (the run itself may show as successful/green, not red).

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
| `Caddyfile` | HTTPS, routing and security headers. `www.<domain>` permanently redirects to the main domain. |
| `.env.example` | Every setting the server needs. Copy it to `/opt/invoflow/.env` on the server. |
| `backup/` | Daily `pg_dump` to R2 (`backup.sh`) and the restore script (`restore.sh`). |
| `server-setup.sh` | One-time hardening of a fresh Ubuntu 24.04 server. |
| `apply-caddy.sh` | Used by the deploy: validates the new `Caddyfile`, then reloads Caddy (or recreates it). |
| `rehearsal/` | The whole stack on your laptop, with no accounts: `./rehearsal/rehearse.sh`. |

## Accounts and who creates them

Gildo creates the accounts, because they need payment or identity. Claude never handles the real keys.

1. **Server:** Hetzner Cloud CX22 or similar, Ubuntu 24.04, in an EU location (Germany or Finland). Add your own SSH key when you create it.
2. **Domain:** point it at Cloudflare DNS. Add an `A` record for the domain and for `www` (and `AAAA` records if the server has IPv6) to the server's IP, with **DNS only** (grey cloud), so Caddy can get its certificate.
3. **Cloudflare R2:**
   - Create the buckets `invoflow-documents` and `invoflow-backups` in the **EU jurisdiction**.
   - Turn on **object versioning** for `invoflow-documents`.
   - Create an R2 API token with Object Read & Write on both buckets.
   - Under CORS on `invoflow-documents`, allow `PUT` and `GET` from `https://<your domain>`. Browsers upload straight to R2.
   - Leave `R2_ENDPOINT_URL` and `BACKUP_ENDPOINT_URL` empty. The API and the backup script then use the EU jurisdiction endpoint `https://<account_id>.eu.r2.cloudflarestorage.com`. Set either variable to `https://<account_id>.r2.cloudflarestorage.com` only when the bucket is in Cloudflare's default jurisdiction.
4. **Clerk:** create a production instance for the domain. You need the publishable key (`pk_live_…`), the secret key (`sk_live_…`) and the Frontend API host. The API accepts a session token only when its `iss` is `https://<CLERK_FRONTEND_API>` and its `azp` is one of `CLERK_AUTHORIZED_PARTIES` (usually `https://<your domain>`). It refuses to start when either is unset.
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
   - **Variable:** `CLERK_PUBLISHABLE_KEY` = `pk_live_…`. This must be a repository variable, not a secret. The publishable key is built into the browser bundle, so it is meant to be public. The workflow treats it as set only when the value, after trimming whitespace, starts with `pk_live_` (the check is case-sensitive). The image build receives that trimmed value. A live key is required. Until it is set, the images and deploy jobs are skipped (the run itself may show as successful/green, not red). A demo bundle is a separate build with `NEXT_PUBLIC_DEMO_AUTH=1`, and production does not set that flag.
   - **Environment:** create one named `production`. You can make it require your approval before every deploy.
5. Run **Actions → Deploy → Run workflow**, or merge anything to `main`. Images build and push to GHCR only when the repository variable `CLERK_PUBLISHABLE_KEY` is set and, after trimming whitespace, starts with `pk_live_` (a live key is required; the check is case-sensitive). The frontend image is built with that trimmed value, and only for a push in this repository (a fork pull request never builds or deploys). Deploy runs only when `DEPLOY_HOST` is set too: the workflow copies the stack files to `/opt/invoflow`, pulls the new `api` and `web` images and runs `docker compose up -d`, which recreates only the services whose image or settings changed (usually `api` and `web`). Caddy is handled by `apply-caddy.sh`. Before anything restarts, `apply-caddy.sh validate` checks the new `Caddyfile` in a throwaway container. If it is invalid, or a throwaway caddy container can't start (a docker or image problem, reported separately), the deploy stops and the running Caddy keeps its current config. After `up -d`, `apply-caddy.sh apply` runs `caddy reload`, which doesn't drop connections. The copy writes files in place (`overwrite: true`), so the running container normally sees the new file. If it doesn't (its copy differs from the one on disk) or the reload fails, the script recreates the `caddy` container instead, which means a second or two of downtime. Certificates survive in the `caddy_data` volume. If that fails too, the deploy fails and prints the caddy logs. The deploy also strips stray spaces around `DOMAIN` in `.env`. `deploy/tests/apply-caddy.test.sh` tests this logic in CI against a fake `docker`, and `deploy/tests/deploy-wiring.test.sh` checks that the workflow validates before `up -d` and applies after it. The API runs `alembic upgrade head` before serving, and the workflow waits for the in-container readiness check at `http://127.0.0.1:8000/health/detailed` (5 second timeout). Caddy exposes `/health` and `/health/detailed` publicly, and the API rate limits `/health/detailed` per IP.

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

## Health checks

| Path | Use it for | Checks | Answers |
|---|---|---|---|
| `/health` | Liveness: is the process up? Restart the container if it fails. | OCR configuration only, no database. | 200, or 503 when OCR is misconfigured. |
| `/health/detailed` | Readiness: send traffic only while it is 200. Point a load balancer here. | OCR configuration and a `SELECT 1` on the database (Postgres or SQLite). | 200, or 503 with `"checks": {"database": "down"}` when the database is unreachable. |

The body never contains the connection string or the database error; the API logs only the error type. Caddy forwards `/health` and `/health/*`, so both are public. `/health/detailed` is limited per client IP (`RATE_LIMIT_HEALTH`, default 30/minute; over the limit you get 429 + Retry-After) because it runs a database query. The Deploy workflow probes `/health/detailed` after rollout. The compose api healthcheck stays on `/health` (liveness).

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
