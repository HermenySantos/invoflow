# COPY-v4.3: v5 UI labels (Conversion Lead sign-off)

Date: 2026-10-18 13:30 Lisbon. Source: DESIGN-SPEC.md, "v5 visual pass", "New UI labels". PT-PT and EN (British). Each string is in one locale only.

| Key | PT (approved) | EN (approved) | Status / why |
|---|---|---|---|
| replay | Repetir | Replay | OK as is |
| rBase | **Líquido** | Net | CHANGED from "Base" to match the app's real export column "Líquido (EUR)" (Invoflow Operator, main 441b3dd). The page uses the product's own words. |
| rVat | **IVA** | **VAT** | CHANGED from "IVA 23%". One fixed rate in the header suggests the app only handles 23%. Real invoices mix 6/13/23%. The rows can stay at 23%. |
| withInvoflow | Com a Invoflow | With Invoflow | OK as is |
| appUpload | Carregar | Upload | OK as is |
| appReceipts | **Faturas** | **Invoices** | CHANGED from "Recibos". For trabalhadores independentes, "recibo" means the recibo verde they issue, not the expense invoices this screen lists. |
| appVat | **Estimativa** | **Estimate** | CHANGED from "IVA". The screen shows a figure, and every IVA figure must read as an estimate (brief + CVO rule). |
| appTake | **Fotografar ou carregar PDF** | **Take a photo or upload a PDF** | CHANGED. Photo first, to match the page's "fotografe" story. No QR claim implied. |
| appReady | Pronto | Ready | OK. Confirmed as the real state label (receipts filters + Estado column). Where a screen shows a count summary, use the app's plural "Prontos". |
| appReview | Por rever | **Needs review** | PT confirmed as the real state label. EN changed from "To review" (more natural British English). |
| appLowConf | **Leitura incerta · reveja** | **Unclear read · check it** | CHANGED. Turns a technical warning into the action, in line with "pode rever e corrigir". |
| packShort | Pack para o contabilista | Pack for your accountant | OK. It isn't "pronto para o contabilista" (banned). check.mjs must still pass. |
| orig | originais | originals | OK as is |
| csvHead | **Data;Fornecedor;Líquido (EUR);IVA (EUR)** | **Date; Supplier; Net (EUR); VAT (EUR)** | CHANGED. These are real summary.csv column names in their real order (export.py, main 441b3dd). The doc caption adds: PT "Algumas colunas do ficheiro." / EN "Some of the file's columns, translated." The file itself is PT-PT only, so the EN version must read as a translation. |
| period (EN) | T4 · 2026 | Q4 · 2026 | OK as is |

## Figure scope
UI Lead relayed that on 2026-10-18 Gildo approved labelled fictional figures ("Exemplo · dados fictícios") in the phone screens, CSV/PDF example docs and gains estimate mini, not only the hero sheet. Recorded on that relay; copy has no objection. Every surface keeps the label, and every IVA figure keeps "estimativa". Confirmation asked of Gildo in chat 2026-10-18.

## Checks
- Run v5/tools/copycheck.mjs and site check.mjs against these strings (new phrases need Crazy QA approval).
- Changelog v4.3 (final, 2026-10-18 13:31): 15 UI labels signed off, 8 changed: rBase, rVat, appReceipts, appVat, appTake, appReview EN, appLowConf, csvHead (+ caption). Pronto/Por rever confirmed against the app (main 441b3dd). Note: the real export has an 'IVA dedutível (EUR)' column, but page copy still never promises 'IVA dedutível' (brief rule), so don't show that column in the example doc.
