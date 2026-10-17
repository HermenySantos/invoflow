# Pilot page

This folder is a static page for the Invoflow pilot. It does not change the app at `/`. The canonical URL is `https://invoflow.pt`. Preview hosts may serve the same files. The canonical link, `og:url`, and `sitemap.xml` keep that name.

The page stores nothing while `FORM_ENDPOINT` is empty. There is no account, no secret, and no third-party script in the default configuration.

## Deploy

The files in this folder are the site. There is no compile step. Use the same build command and output directory on either host. Set the project root directory to `site` in both dashboards. Do not change DNS from this repository.

| Host | Build command | Output directory |
| --- | --- | --- |
| Cloudflare Pages | empty | `.` |
| Vercel | empty | `.` |

On Vercel, set the framework preset to Other. `vercel.json` in this folder marks the project as static HTML (`framework` is null) and turns on clean URLs, so `/privacy` matches the Cloudflare path.

Cloudflare Pages reads `functions/` from this folder. Vercel does not run that Pages Function. The static page still loads, and the form keeps the empty-endpoint notice until `FORM_ENDPOINT` is set.

A pull request does not deploy this folder. The existing app workflow builds `frontend/` and `backend/` only. Attaching invoflow.pt is a dashboard and DNS step, and it is outside this repository.

## Configure the form

Edit `js/config.js`. Publish a new deployment after each change.

| Constant | Default | What to set |
| --- | --- | --- |
| `FORM_ENDPOINT` | empty | `/api/signup` after the function below has a binding. Any other URL also works if you widen `connect-src` in `_headers`. |
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

Plausible, when enabled, receives the event names above. The Meta pixel, when enabled, records a page view. Adding either one needs a wider content security policy in `_headers`:

- Plausible: `script-src` and `connect-src` must allow `https://plausible.io`.
- Meta: `script-src` must allow `https://connect.facebook.net`. `connect-src` and `img-src` must allow `https://www.facebook.com`.

## Signup function

`functions/api/signup.js` is an optional Pages Function. It is not bound to a Cloudflare account in this repository.

It accepts the form JSON and writes one record.

- KV binding: `SIGNUPS`. The signup key is a random id. The value is the JSON record. A second key, `email:` plus the normalized email, points at that id.
- D1 binding: `DB`. Create both tables, then the function inserts a row.

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

If neither binding exists, the function returns HTTP 501 and writes nothing. Point `FORM_ENDPOINT` at `/api/signup` only after one binding is in place.

The function calculates `qualified` again. A value sent by the browser does not override that result.

The email is stored in lowercase with surrounding spaces removed. A second request for that email returns HTTP 200 and the same thank-you, and it does not write another row.

The form includes a hidden `leave_blank` field. When that field has text, the function returns HTTP 200 and writes nothing.

Each IP address can submit 5 requests an hour. The function stores SHA-256 of the address, not the address, and the KV entry expires within the hour. The sixth request in that hour returns HTTP 429. A body larger than 8192 bytes returns HTTP 413. A body that is not a JSON object, or that fails the form rules, returns HTTP 400.

## Check

From the repository root:

```bash
node site/check.mjs
```

CI runs the same command. It rejects banned marketing lines, unexpected euro amounts, a second copy of the qualification rule, and the scarcity line.

## Demo recording

`tools/record-demo.mjs` drives the local app in mock mode and writes `assets/demo-short.mp4`, `assets/poster.jpg`, and the caption tracks. Install Playwright in this folder first (`npm install playwright`), with the app already running at `http://127.0.0.1:3000`. The script signs in as `demo@invoflow.test`, uploads one fictional invoice, and checks the picture for the filing dates and the estimate label.
