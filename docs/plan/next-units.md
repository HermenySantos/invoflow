# Next units

Follow-ups to the e-Fatura test pull and the quarter-to-date IVA projection. Each item is one Linear issue. None of them is part of the spike.

## 1. Show the e-Fatura link on the receipt

The pull already writes an `efatura_links` row and an audit event when a consultation matches a scanned receipt. The receipt screen does not show that yet.

Acceptance criteria:

- A receipt with a link whose outcome is `linked_existing` or `linked_hidden` shows the link warning and the `source_key`.
- The screen does not copy AT amounts, the supplier name, or the invoice number onto the receipt.
- `_same_receipt` and the importer's match order stay as they are.
- A receipt with no link renders as it does today.

## 2. Copy AT figures only when the user asks

Import links a match and leaves the scanned figures in place. Replacing them has to be a separate action.

Acceptance criteria:

- An explicit action copies issuer name, invoice number, date, net, VAT, and gross from the link's `payload_json` onto that receipt.
- The action is refused when the link has no document, the document is hidden, or the payload has no totals.
- The copy writes an audit row with source `efatura` and the previous values.
- `import_purchases` still does not copy fields.

## 3. Apply a credit note without a negative VAT amount

An acquirer `NC` is stored as a link and is not an expense, because a positive credit note would increase deductible VAT and a negative `vat_amount` is rejected by the edit API.

Acceptance criteria:

- An acquirer `NC` can reduce the deductible VAT of one linked purchase without storing a negative `vat_amount`.
- The edit API still rejects a negative amount.
- A credit note with no matching purchase stays a link and does not become a receipt.
- The effect stays in `needs_review` until Gildo has reviewed the reduction. It does not enter confirmed deductible VAT before that.

## 4. SOAP client for the AT test environment

The spike selects a SOAP adapter and does not connect. The real call waits on sandbox access.

Acceptance criteria:

- With `EFATURA_PULL_ENABLED` on, a non-empty endpoint, and username, password, and AT public key set, `fetch` calls the test consultation on port 725 and returns `EFaturaInvoice` values.
- An endpoint that uses production port 425 is rejected before a request is sent.
- A missing username, password, or AT public key still fails before a socket opens.
- No certificate, password, or private key is committed.
- An empty endpoint still uses the fixture.
- This issue stays blocked until Gildo provides test-environment access and the client certificate.

## 5. One sandbox credential per taxpayer

The settings object holds a single username and password for the whole process.

Acceptance criteria:

- A pull for one user cannot authenticate as another user's sub-user.
- The secret is not a password column on `efatura_subjects`. It lives in the environment or a secret store, keyed by taxpayer.
- Empty defaults still boot, and the pull stays off unless the flag is on.
- The fixture path does not require a secret.

## 6. Article 21 exceptions after review

The category comment names congress, fair, electric-vehicle, and charging exceptions. No category implements them. Unknown fuel stays on the current percentage because a pulled row has no receipt text.

Acceptance criteria:

- No new deductibility percentage is added until Gildo reviews art. 21(2)(d), (e), (f), and (h).
- Unknown fuel keeps the current rule.
- `project_quarter_to_date` still does not import the category table.
- Any new wording calls the figure an estimate and does not call it accountant-ready.
