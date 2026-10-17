# Pilot page

This folder is a static page for the Invoflow pilot. It does not change the app at `/`. The canonical URL is `https://invoflow.pt`. Preview hosts may serve the same files. The canonical link, `og:url`, and `sitemap.xml` keep that name.

The page stores nothing while `FORM_ENDPOINT` is empty. There is no account, no secret, and no third-party script in the default configuration.

## Deploy

The published files are in `public/`. There is no compile step. Set the project root directory to `site` in both dashboards, and set the output directory to `public`. `README.md`, `check.mjs`, and `tools/` stay outside that directory, so they are not served. Do not change DNS from this repository.

| Host | Build command | Output directory |
| --- | --- | --- |
| Cloudflare Pages | empty | `public` |
| Vercel | empty | `public` |

On Vercel, set the framework preset to Other. `vercel.json` in this folder marks the project as static HTML (`framework` is null) and turns on clean URLs, so `/privacy` matches the Cloudflare path.

Cloudflare Pages reads `functions/` from this folder, next to `public/`, not from inside it. A missing path serves `public/404.html` with status 404. Vercel does not run that Pages Function. The static page still loads, and the form keeps the empty-endpoint notice until `FORM_ENDPOINT` is set.

A pull request does not deploy this folder. The existing app workflow builds `frontend/` and `backend/` only. Attaching invoflow.pt is a dashboard and DNS step, and it is outside this repository.

## Configure the form

Edit `public/js/config.js`. Publish a new deployment after each change.

| Constant | Default | What to set |
| --- | --- | --- |
| `FORM_ENDPOINT` | empty | `/api/signup` after the function below has a binding. Any other URL also works if you widen `connect-src` in `public/_headers`. |
| `DEPOSIT_ENABLED` | `false` | `true` only when you also set the Stripe link. |
| `STRIPE_PAYMENT_LINK` | empty | A Stripe Payment Link for the €19 refundable reservation. The amount is taken off the first quarter. |
| `ANALYTICS` | empty | `plausible` to load Plausible. |
| `PLAUSIBLE_DOMAIN` | empty | The domain Plausible should record. |
| `META_PIXEL_ID` | empty | The numeric Meta pixel id for the ad test. |

While `FORM_ENDPOINT` is empty, the page shows a notice and does not send or store the submission.

While `DEPOSIT_ENABLED` is false, the page does not mention the €19 reservation.

## Analytics events

Nothing is sent until `ANALYTICS` or `META_PIXEL_ID` is set.

| Event | When it fires |
| --- | --- |
| `visit` | The page script starts. |
| `cta_click` | A person follows a "Reservar" link to the form. |
| `form_submit` | The form is valid. This includes the case where the endpoint is empty and nothing is stored. |
| `qualified_submit` | The same moment, and only when the request is qualified. |

Qualified means quarterly VAT, 20 or more invoices a month, and an accountant. Consent is required to submit and is not part of that rule.

Plausible, when enabled, receives the event names above. The Meta pixel, when enabled, records a page view. Adding either one needs a wider content security policy in `public/_headers`:

- Plausible: `script-src` and `connect-src` must allow `https://plausible.io`.
- Meta: `script-src` must allow `https://connect.facebook.net`. `connect-src` and `img-src` must allow `https://www.facebook.com`.

## Signup function

`functions/api/signup.js` is an optional Pages Function. It is not bound to a Cloudflare account in this repository. Vercel does not run it. The function stores rows only in D1. A KV binding is ignored and does not receive signups.

Create both tables on the D1 database bound as `DB`:

```sql
CREATE TABLE signups (
  id TEXT PRIMARY KEY,
  email TEXT NOT NULL,
  payload TEXT NOT NULL,
  received_at TEXT NOT NULL
);
CREATE UNIQUE INDEX signups_email ON signups (email);

CREATE TABLE signup_rates (
  ip_hash TEXT PRIMARY KEY,
  count INTEGER NOT NULL,
  reset_at INTEGER NOT NULL
);
```

Set `IP_HASH_SECRET` in the Cloudflare environment. The function uses it as the HMAC-SHA-256 key for the address summary. Do not commit a value for that secret. If `DB` or `IP_HASH_SECRET` is missing, the function returns HTTP 501 and writes nothing. Point `FORM_ENDPOINT` at `/api/signup` only after both are in place.

`SIGNUP_ORIGINS` is optional. When it is set, it is a comma-separated list of allowed `Origin` values, matched exactly. When it is unset, the `Origin` host must equal the host of the request URL. A missing or other origin returns HTTP 403.

The request must send `Content-Type: application/json` and `CF-Connecting-IP`. The function does not read `X-Forwarded-For`. A missing address returns HTTP 400. IPv4 addresses are counted as written. IPv6 addresses share one counter for each `/64`. An IPv4-mapped address is counted as that IPv4 address.

Each address can submit 5 requests an hour. The stored key is the HMAC of that bucket, not the address. The sixth request returns HTTP 429 with a short message in Portuguese and in English. The next write deletes rate rows whose window ended more than an hour ago. The current address is reset in the same upsert instead of being deleted.

The function calculates `qualified` again. A value sent by the browser does not override that result.

The email is stored after Unicode NFKC, lowercasing, and punycode on the domain. One trailing dot on the domain is removed. A second request for that email returns the same HTTP 200 body and does not write another row.

The form includes a hidden `extra` field. When that field has text, the function still touches the database and returns the same HTTP 200 body, `{"ok":true}`, with no id. A first accepted signup returns that same body.

A body larger than 8192 bytes returns HTTP 413. A body that is not a JSON object, or that fails the form rules, returns HTTP 400. Function responses send `X-Content-Type-Options: nosniff` and `Cache-Control: no-store`.

## Check

From the repository root:

```bash
node site/check.mjs
```

CI runs the same command. It rejects banned marketing lines, unexpected euro amounts, a second copy of the qualification rule, and the scarcity line.

## Demo recording

`tools/record-demo.mjs` drives the local app in mock mode and writes `public/assets/demo-short.mp4`, `public/assets/poster.jpg`, and the caption tracks. Install Playwright in this folder first (`npm install playwright`), with the app already running at `http://127.0.0.1:3000`. The script signs in as `demo@invoflow.test`, uploads one fictional invoice, and checks the picture for the filing dates and the estimate label.
