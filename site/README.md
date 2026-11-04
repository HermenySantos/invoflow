# Pilot page

This folder is a static page for the Invoflow pilot. It does not change the app at `/`. The canonical URL is `https://invoflow.pt`. Preview hosts may serve the same files. The canonical link, `og:url`, and `sitemap.xml` keep that name.

The page stores nothing while `FORM_ENDPOINT` is empty. There is no account, no secret, and no third-party script in the default configuration.

## Deploy

The published files are in `public/`. There is no compile step. In both dashboards set the root directory to `site` and the build output directory to `public`. `README.md`, `check.mjs`, `vercel.json`, and `tools/` stay outside that directory, so they are not served. Do not change DNS from this repository.

| Host | Build command | Output directory |
| --- | --- | --- |
| Cloudflare Pages | empty | `public` |
| Vercel | empty | `public` |

On Vercel, set the framework preset to Other. `vercel.json` in this folder marks the project as static HTML (`framework` is null), turns on clean URLs, and keeps a trailing slash. `/privacy` is one 308 to `/privacy/`. The same hop is in `public/_redirects` and in the Pages middleware, so Cloudflare does not add a second redirect.

Cloudflare Pages reads `functions/` from this folder, next to `public/`, not from inside it. A missing path serves `public/404.html` with status 404. `functions/assets/[[path]].js` answers `Range` on `.mp4` files with status 206. That catch-all, and every 404, drops `s-maxage` from `Cache-Control`. `/404.html` is `no-store`. `/.env`, `/.git/config`, `/admin`, and a path that contains `//` return status 404. `public/_routes.json` includes every path, so the guard sees `/privacy//`, `//`, and `/css//site.css`. An exclude of the collapsed file would let Pages serve that doubled path as the static file. Vercel does not run that Pages Function. The static page still loads, and the form keeps the empty-endpoint notice until `FORM_ENDPOINT` is set.

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
| `cta_click` | A person follows an "Avisem-me" or "Keep me posted" link to the form. |
| `form_submit` | The form is valid. This includes the case where the endpoint is empty and nothing is stored. |

The form asks for an email and consent. It does not ask for a name, a VAT regime, an invoice band, or an accountant, and it does not mark a request as qualified.

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

Set `IP_HASH_SECRET` in the Cloudflare environment. The function uses it as the HMAC-SHA-256 key for the address summary. Do not commit a value for that secret. The function checks `Content-Type: application/json` and `Origin` before it looks at the bindings. A cross-origin request returns HTTP 403, and a non-JSON request returns HTTP 400, including when `DB` or `IP_HASH_SECRET` is missing. If those bindings are missing and the request is allowed, the function returns HTTP 501 and writes nothing. Point `FORM_ENDPOINT` at `/api/signup` only after both are in place.

`SIGNUP_ORIGINS` is optional. When it is set, it is a comma-separated list of allowed `Origin` values, matched exactly. When it is unset, the `Origin` host must equal the host of the request URL. A missing or other origin returns HTTP 403.

The request must send `Content-Type: application/json` and `CF-Connecting-IP`. The function does not read `X-Forwarded-For`. A missing address returns HTTP 400. IPv4 addresses are counted as written. IPv6 addresses share one counter for each `/64`. An IPv4-mapped address is counted as that IPv4 address.

Each address can submit 5 requests an hour. The stored key is the HMAC of that bucket, not the address. The sixth request returns HTTP 429 with a short message in Portuguese and in English. The next write deletes rate rows whose window ended more than an hour ago. The current address is reset in the same upsert instead of being deleted.

A stored row holds the normalized email, a server consent timestamp, the consent text version `copy-v4.2-2026-10-17`, the language, and `utm_source`, `utm_medium`, and `utm_campaign` when those values are present. The server writes the version. A client-sent version, name, regime, volume, accountant, or timestamp is not stored. There is no outbound email and no double opt-in.

The email is stored after Unicode NFKC, lowercasing, and punycode on the domain. One trailing dot on the domain is removed. A second request for that email returns the same HTTP 200 body and does not write another row.

The form includes a hidden `extra` field. When that field has text, the function still touches the database and returns the same HTTP 200 body, `{"ok":true}`, with no id. A first accepted signup returns that same body.

A body larger than 8192 bytes returns HTTP 413. A body that is not a JSON object, or that fails the form rules, returns HTTP 400. Function responses, including the guard 404, the signup responses, and the video range responses, send the same security headers as `public/_headers`. Signup responses also send `Cache-Control: no-store`.

## Check

From the repository root:

```bash
node site/check.mjs
```

CI runs the same command, including `tools/copycheck.mjs` against COPY-v4 and the 15 signed-off UI labels. It rejects banned marketing lines, and a price written as `€`, `EUR`, `euro`, or `euros` outside an element or caption cue labelled example or estimate. `23%` is not a price. The scan includes the pages, the caption files, and the meta and Open Graph tags. It also rejects qualification fields and the scarcity line. `node site/check.mjs --release` also fails while a `.token` chip or a bracket token remains on the home page, `js/copy.js`, or the privacy page. The site job does not pass `--release`.

## Demo recording

`tools/record-demo.mjs` drives the local app in mock mode and writes `public/assets/demo-short.mp4`, `public/assets/poster.jpg`, and the caption tracks. Install Playwright in this folder first (`npm install playwright`), with the app already running at `http://127.0.0.1:3000`. The script signs in as `demo@invoflow.test`, uploads one fictional invoice, and checks the picture for the filing dates and the estimate label.
