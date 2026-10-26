# OCR corpus accuracy

Counted cells come from two unique text layouts, `fatura-cafe-lisboa.pdf` and `nota-credito.pdf`.

`123456002` is a synthetic placeholder, not verified unissued. Decreto-Lei n.º 14/2013, artigo 4.º, n.º 2, assigns a first digit of 1, 2, 3 or 4 to a pessoa singular, so this number is not a company NIF. The café fixture names the supplier Ana Costa. The credit note prints `501111111`, which fails the check digit, so that NIF cell stays empty.

## What is counted

A cell counts when the layout is unique and the fixture expects a value. The `.qpdf.pdf` files repeat those two layouts and are read, not scored. The thermal roll and the photo add 14 cells that come from the QR payload. Those cells are flagged, not counted. Empty expected cells are flagged, not counted. On the unique credit note that is net, IVA, and rate.

Counted cells: 11. The café invoice has 7. The credit note contributes NIF, date, invoice number, and gross.

Net 10.00 and rate 23.00 on the café invoice are implied from the printed total and IVA. They are expected values, not empty cells.

The credit-note total is printed as `Total: -10,00`. The stored amount is the absolute value. Without an AT QR the document stays unclassified and needs manual review. The invoice-number cell in this table is a suggestion used to prefill the review screen, not a confirmed number. A hyphen glued to a label, such as `Total-12,30`, is not a minus.

## Before the extractor changes

The before column runs `tests/ocr_extract_baseline.py`, a snapshot of the extractor at merge-base 441b3dd, on the text layer of these two layouts. It is scored against the same expected cells. The hits are computed by that run.

| field | hits | counted | accuracy |
| --- | --- | --- | --- |
| NIF | 1 | 2 | 50.0% |
| date | 0 | 2 | 0.0% |
| invoice number | 0 | 2 | 0.0% |
| net | 1 | 1 | 100.0% |
| IVA | 1 | 1 | 100.0% |
| gross | 2 | 2 | 100.0% |
| rate | 1 | 1 | 100.0% |
| all | 6 | 11 | 54.5% |

Before, on these fixtures: 6 of 11 (54.5%).

An earlier draft of this file scored 40 of 42 cells (95.2%), and 16 of 28 raster cells (57.1%). That draft counted the qpdf copies, 14 QR-only cells, 6 empty-equals-empty cells, and the credit-note gross. It is not the score.

## After, production path

What `OCRService.process_document` returns with `OCR_BACKEND=tesseract` on the two unique text layouts. Text PDFs use the text layer. QR documents are not in this table.

| field | hits | counted | accuracy |
| --- | --- | --- | --- |
| NIF | 1 | 2 | 50.0% |
| date | 2 | 2 | 100.0% |
| invoice number | 2 | 2 | 100.0% |
| net | 1 | 1 | 100.0% |
| IVA | 1 | 1 | 100.0% |
| gross | 2 | 2 | 100.0% |
| rate | 1 | 1 | 100.0% |
| all | 10 | 11 | 90.9% |

| document | NIF | date | invoice number | net | IVA | gross | rate |
| --- | --- | --- | --- | --- | --- | --- | --- |
| fatura-cafe-lisboa.pdf | hit 123456002 | hit 2026-03-31 | hit FT A/12 | hit 10.00 | hit 2.30 | hit 12.30 | hit 23.00 |
| nota-credito.pdf | miss None | hit 2026-04-15 | hit NC Q2 | flagged empty | flagged empty | hit 10.00 | flagged empty |

Counted result: 10 of 11 (90.9%).

## Flagged, not counted

| document | why | cells |
| --- | --- | --- |
| fatura-cafe-lisboa.qpdf.pdf | same text as fatura-cafe-lisboa.pdf | not scored |
| nota-credito.qpdf.pdf | same text as nota-credito.pdf | not scored |
| thermal-80mm.pdf | QR payload only | 7 flagged |
| fatura-photo.png | QR payload only | 7 flagged |
| nota-credito.pdf | empty net, IVA, and rate | 3 flagged |

## Raster check

Tesseract `por+eng` on the first page of each unique PDF, with the QR payload not applied, agreed with the text-layer read on the counted cells.

## Follow-ups

- The credit-note fixture prints NIF 501111111. That number fails the check digit, so the extractor leaves the NIF empty. The check stays.
- Vendor lines still keep the first heading (`Fornecedor: Ana Costa`, `Nota de crédito NC Q2`) instead of the name after Fornecedor.
- The credit note prints no net, IVA, or rate. Those three cells stay flagged.
- On the thermal roll and the photo, the pipeline amounts come from the QR. Tesseract on the roll itself only has the word Talão plus the QR image.
- Month names cover `d de mês de yyyy` and abbreviations such as `set` and `fev.`. Other date layouts are unchanged.
- Crumpled photos and digit mixups are not in this corpus.

## Suggestions

Type and number suggestions are scored on their own. A blank suggestion is a counted cell when the layout must not suggest a type or a number. These cells are not confirmed document types or numbers.

The two original PDFs stay in the field table above. The extra layouts are synthetic: fictional shop names, and NIF `123456002` printed as a placeholder. Text-layer rows are what the PDF text produces. Rendered rows are Tesseract `por+eng` on a DejaVu drawing of the same kind of wording, including the credit-note wordings from the QA gates.

| layout | read | type suggestion | number suggestion |
| --- | --- | --- | --- |
| fatura-cafe-lisboa.pdf | text layer | hit FT | hit FT A/12 |
| nota-credito.pdf | text layer | hit NC | hit NC Q2 |
| fs-quiosque.pdf | text layer | hit FS | hit FS B/3 |
| fr-oficina.pdf | text layer | hit FR | hit FR C/9 |
| nd-armazem.pdf | text layer | hit ND | hit ND D/2 |
| nc-mirante.pdf | text layer | hit NC | hit NC Q2/7 |
| nc-wording-nota-credito.pdf | text layer | hit blank | hit blank |
| nc-wording-footer.pdf | text layer | hit blank | hit blank |
| nc-wording-a-favor.pdf | text layer | hit blank | hit blank |
| nc-wording-euro.pdf | text layer | hit blank | hit blank |
| nc-wording-qualifier.pdf | text layer | hit blank | hit blank |
| thermal-fs.pdf | text layer | hit FS | hit FS T/1 |
| render-footer-credito.png | tesseract | hit blank | hit blank |
| render-credito-a-favor.png | tesseract | hit blank | hit blank |
| render-n-slash-c.png | tesseract | hit blank | hit blank |
| render-nota-credito.png | tesseract | hit NC | hit NC Q2/7 |
| render-thermal-fs.png | tesseract | hit FS | hit FS T/1 |
| render-fatura-recibo.png | tesseract | hit FR | hit FR C/9 |
| render-nota-debito.png | tesseract | hit ND | hit ND D/2 |

Suggestion cells: 38 of 38 (100.0%).
