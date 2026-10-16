# e-Fatura test-environment pull and quarter-to-date IVA prediction

## Design decision

The shape implemented here is **link, then warn**. A second sketch scaled the whole quarter payable, changed the summary's month math, and changed the existing duplicate matcher. Those edits are not in this change. The sentence kept from that sketch is the Portuguese disclaimer that the projection is not a tax filing.

Both sketches were written by the same model family after the other review seats were rejected for usage limits, so this choice was made against the product constraints rather than by a second-family judge: do not change `estimated_iva_payable`, do not merge a scan and an e-Fatura row into one set of figures, and do not add a tax rule.

## Architecture

Invoflow already turns a file into one `documents` row and estimates IVA as the user's quarter (or month) `VatSalesEntry` minus confirmed deductible VAT. Confirmed means `ready` and `accountant_review`, through `effective_deductible_pct`. This PR puts e-Fatura purchases on that same row and adds a projection beside the estimate. It does not retune the estimate.

Two modules own the new behavior.

`app/services/efatura.py` is the only writer. `build_efatura_client` picks a fixture adapter or a SOAP adapter that does not connect. `import_purchases` decides which consultation rows are expenses, inserts a `Document` when the purchase is new, and always records an `efatura_links` row. Callers cannot pass a review status, a file key, or a sales total. The route is the shell: authenticate, refuse when the flag is off, fetch, import, commit.

`app/services/iva_projection.py` is a pure function, `project_quarter_to_date`. It never sees a document or a tax table. `GET /api/summary/projection` loads the confirmed deductible total with the existing `deductible_vat_split`, on a quarter clipped to `as_of`, and passes that number in. `get_summary` and the export keep the full calendar window.

Nothing runs at startup. `lifespan` still only resumes receipts left in `processing`. The pull is off unless `EFATURA_PULL_ENABLED` is true, and even then only `POST /api/efatura/pull` runs it.

```text
POST /api/efatura/pull
  flag off → 404
  flag on, endpoint empty → fixture fetch
  flag on, endpoint set → SOAP client raises NotImplementedError (no socket)
        │
        ▼
import_purchases
  split on the stored taxpayer NIF
  issuer / credit note / cancelled / incomplete → link only
  one matching receipt → link + warning, scalars untouched
  no match → Document needs_review + link
        │
        ▼
existing readers (unchanged)
  get_summary, deductible_vat_split, export

GET /api/summary/projection
  clip quarter to as_of → deductible_vat_split confirmed half
  quarter VatSalesEntry or None
        │
        ▼
project_quarter_to_date → IVA previsto (estimativa)
```

## Data model

`documents` stays the receipt. A new purchase fills the columns the estimate already reads: issuer NIF as `vendor_nif`, document number as `invoice_number`, issue date, net, summed IVA, gross, one VAT rate or null, category from `categorize_document`. `status` is the review state `needs_review`. Fiscal type and fiscal status are not stored there.

`storage_key`, `original_filename`, and `mime_type` are required, and there is no file. The row uses a sentinel key `efatura/{user_id}/{source_key}`, a `.efatura` filename, and mime type `application/vnd.invoflow.efatura+json`. Export already skips a key the object store does not have and still writes the CSV line. The sentinel does not start with the Clerk id because the row is not created through the upload API.

`ocr_raw_response` is `{"source":"efatura"}` so fuel detection, which reads the `text` key, does not see a fabricated receipt. The VAT lines are not copied there.

`efatura_subjects` stores the account's taxpayer NIF, one row per user, `String(36)` user id. The pull compares it to issuer and acquirer before anything is an expense. There is no password column.

`efatura_links` is the AT identity: `(user_id, source_key)` unique, role, outcome, nullable `document_id`, fiscal status, a warning, and `payload_json`. `source_key` is `atcud:{atcud}` when the consultation sent an ATCUD, otherwise `doc:{issuer_nif}:{type}:{invoice_number}`. ATCUD is not written into `invoice_number`. The link has no money columns, so the payable cannot drift onto a second total. Re-pull updates fiscal status on the link and leaves the receipt alone.

Ids are `String(36)`. Migration `007_efatura_links` upgrades and downgrades. Both models are imported from `app/models/__init__.py`.

New purchases land as `needs_review` on purpose. The consultation does not promise a supplier name, a person has not checked the row, and `needs_review` is the bucket `get_summary` already reports as pending. The payable does not move until someone sets `ready` or `accountant_review` through the existing edit API. A nameless supplier that misses the ten-NIF map is category `other` at 0% until someone categorizes it. The row is still on the receipt list, in `total_vat`, and in the export CSV.

## AT test-environment auth

Auth is configuration, and the configuration ships empty.

| Setting | Default | Role |
| --- | --- | --- |
| `EFATURA_PULL_ENABLED` | false | Off means the route is 404 and no adapter is built |
| `EFATURA_ENDPOINT` | empty | Test consultation URL when a later PR connects |
| `EFATURA_USERNAME` | empty | Sandbox sub-user, `NIF/subuser` |
| `EFATURA_PASSWORD` | empty | Sandbox password |
| `EFATURA_AT_PUBLIC_KEY_PEM` | empty | AT authentication public key |
| `EFATURA_CLIENT_CERT_PEM` | empty | Software client certificate, unused here |
| `EFATURA_CLIENT_KEY_PEM` | empty | Software client key, unused here |

No feature-flag SDK. No secret in the repo. Boot does not require any of these. `validate_configuration` warns only when the pull is enabled, an endpoint is set, and username, password, or the AT public key is still empty. It does not refuse to start.

The real adapter is selected only when the endpoint is non-empty and those three values are present, and its `fetch` raises `NotImplementedError` without opening a socket. An empty endpoint with the flag on is the fixture. The fixture file is read inside `fetch`, not at import.

The documented test endpoint, which is not a default, is `https://servicos.portaldasfinancas.gov.pt:725/fatshare/ws/fatshareFaturas`. Production port 425 is out of this PR.

WS-Security (username token, AES-128-ECB password and timestamp, RSA-wrapped nonce, AT-signed client certificate) belongs inside a future SOAP adapter. It is not a type on `EFaturaClient`. The public method returns `EFaturaInvoice`. The sandbox username and password are one test taxpayer, not a multi-tenant vault. A later production design has to store each user's WFA sub-user secret outside `Settings`. This PR does not build that vault, and it does not call AT.

## Dedupe of OCR and e-Fatura

`_same_receipt` stays as it is. It does not treat "photo has no invoice number, e-Fatura has a number" as a match when the numbered row is the subject, and it ignores soft-deleted rows. The importer does not use it and does not change it.

The importer's match, in order, against this user's documents including hidden ones:

1. ATCUD equal to `ocr_raw_response.qr.atcud`.
2. Same issuer NIF and the same invoice number.
3. Same issuer NIF, the receipt has no invoice number, same date, gross within €0.50.

Vendor name is not a key. Several matches link to nobody and insert nothing. One match inserts a link, writes an audit warning with `source="efatura"`, and does not copy AT numbers onto the working copy. Zero matches insert the `needs_review` receipt.

That is the answer to the research note's "merge" and to the duplicate warning. The rows are associated. They are not fused. A hidden receipt stays hidden. A repeat pull finds `source_key` and does not insert again. A race on the unique constraint becomes `unchanged`.

What this refuses: a second expense that would sit in pending beside the photo, a silent overwrite of a user edit, and a unique index that would turn today's warning into a database reject.

The warning is the pull response, the link's `warning`, and the audit row. This PR does not change `build_document_response`, so the receipt list does not grow a new badge yet.

Issuer invoices, credit notes (`NC`), cancelled documents seen for the first time, negative IVA sums, and rows with no amounts are links without a receipt. A credit note stored as a positive expense would increase deductible VAT. A negative amount is rejected by the edit API and would silently shrink the estimate if it were inserted directly. Neither is stored as an expense.

## IVA prediction

The projection is a labelled estimate of the quarter's confirmed deductible VAT, run forward by the fraction of the quarter still ahead. It is not a new tax rule and it is not the hero number.

`projected_deductible` scales `confirmed_deductible` by `days_in_quarter / days_elapsed`, in `Decimal`, rounded half up to cents. Before the quarter, the projection of deductible VAT is zero. After the quarter, the ratio is one. `projected_iva_payable` is `vat_on_sales - projected_deductible` when the quarter `VatSalesEntry` exists, including when that amount is zero. When the row is missing, `projected_iva_payable` is null. A missing sales figure must not read as a refund. Monthly sales rows are not added together to fill the quarter. Sales are not scaled.

The number is labelled `IVA previsto (estimativa)`. The response carries this disclaimer: "Estimativa linear do IVA do trimestre, obtida a partir do IVA dedutível confirmado até à data. Não é uma declaração fiscal." It is not called accountant-ready. It is not written to `estimated_iva_payable`, `confidence_percent`, the CSV, or the PDF. `confidence_percent` remains the share of receipts in `ready`. It is not a forecast interval.

Deductibility stays `effective_deductible_pct`: the per-receipt override, else the category table, with gasoline at 0% only when the receipt text says so. This PR does not add a congress, fair, or electric-vehicle rule, and it does not store a second deductible percentage. The projection function does not import that table. The route passes it the confirmed total `deductible_vat_split` already computed, so pending `needs_review` receipts, including fresh e-Fatura rows, are outside the run-rate.

Issuer-side VAT stays on the link payload. Nothing in this PR sums it into `VatSalesEntry` or into the projection. Showing a suggested sales figure for the user to type can be a later screen. Writing the entry for them is not part of this one.

## What this PR does not change

- `estimated_iva_payable`, including the `"85.00"` summary test.
- `get_summary`'s month and quarter window.
- `deductible_vat_split` and `effective_deductible_pct`.
- The export ZIP builder, its statuses, and its columns.
- `POST /api/documents`, OCR, and the `processing` resume path.
- Upload duplicate warnings.
- The summary page. There is no UI and no deploy change.

Once a pull has run, existing readers see the new `needs_review` rows. `total_vat`, pending deductible (often 0% while the category is `other`), the receipt list, and the export CSV can change for that user. `estimated_iva_payable` changes only after a person confirms a row that has a non-zero deductible percentage, which is the current rule. Default boot does not pull, so the default suite does not take that path.

## Risks and questions for Gildo

The Article 21 table is not settled. `ABOUT.md` calls the rules accurate. The category comment lists congress organiser 50% (art. 21(2)(d)), participant 25% (art. 21(2)(e)), and electric-vehicle and charging exceptions (art. 21(2)(f) and (h)). No category implements those. Unknown fuel stays at the category 50% because this feed has no receipt text. Unmerged PR #25 and the 15 Oct 2026 operating log both leave that review with Gildo. This PR does not close it. Do not add those branches in the implementation.

Questions:

- Should a pulled purchase with a complete total stay `needs_review` until a person confirms it, which is what this design does, or become `ready` once a supplier name exists?
- Is a linear run-rate of confirmed deductible VAT, against the unscaled quarter sales lump, the projection you want? Nothing in the product history defines one. `ABOUT.md`'s "roughly 500 EUR by the 20th" is cash timing of the current estimate, not this formula.
- May issuer-side invoices later suggest the number the user types into `VatSalesEntry`? This PR stores them and does not write the entry.
- When a pull and a scan are the same invoice, is "link and warn, keep the scanned figures" the right reading of the research note's merge? Copying AT figures onto the receipt is a later explicit action, not this import.
- How should an `NC` reduce an expense without a negative `vat_amount`? This PR skips it.
- Does fiscal status `invoiced` mean a second document we would double-count beside the original? This PR stores it as its own purchase.
- The word "accountant-ready" is still an open wording review. The projection label does not use it.
- Test-environment access is not in this repo: who provisions the AT sandbox sub-user, the WFA permission, and the client certificate, and which taxpayer NIF is allowed on port 725?

Other risks, not questions:

- Most pulled suppliers will not be in the ten-NIF map and will have no name, so they are `other` at 0% until someone categorizes them. That is the current table, not a new rule.
- `confidence_percent` falls as `needs_review` rows are added. It is not the prediction.
- The export CSV will list a pulled receipt, and the ZIP will not contain bytes for the sentinel key. The builder is unchanged.
- A long-lived local `invoflow.db` does not gain these tables from `add_missing_nullable_columns`. CI runs Alembic.
- The sandbox password in the environment is one global test user. Pointing it at a real taxpayer is outside this design.
- Team chat was not part of the record this design was grounded on. A decision already made there would not appear here.
