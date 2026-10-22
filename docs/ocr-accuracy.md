# OCR corpus accuracy

Counted cells come from two unique text layouts, `fatura-cafe-lisboa.pdf` and `nota-credito.pdf`.

`123456002` is a synthetic NIF with a valid mod-11 check digit. It replaces a real company NIF that used to appear in these fixtures. This report does not claim the number was checked against a taxpayer register. The credit note prints `501111111`, which fails the check digit, so that NIF cell stays empty.

## What is counted

A cell counts when the layout is unique and the fixture expects a value. The `.qpdf.pdf` files repeat those two layouts and are read, not scored. The thermal roll and the photo add 14 cells that come from the QR payload. Those cells are flagged, not counted. Empty expected cells are flagged, not counted. On the unique credit note that is net, IVA, and rate.

Counted cells: 11. The café invoice has 7. The credit note contributes NIF, date, invoice number, and gross.

Net 10.00 and rate 23.00 on the café invoice are implied from the printed total and IVA. They are expected values, not empty cells.

The credit-note total is printed as `Total: -10,00`, with a space before the minus. That sign is counted. A hyphen glued to a label, such as `Total-12,30`, is not a minus and is not a gain in this table.

## Before the extractor changes

Same 11 cells, from the measurement taken before month-name dates, series prefixes, and the spaced minus on the credit total. The café invoice missed the date and the invoice number. The credit note missed NIF, date, invoice number, and gross, which was read as 10.00.

| field | hits | counted | accuracy |
| --- | --- | --- | --- |
| NIF | 1 | 2 | 50.0% |
| date | 0 | 2 | 0.0% |
| invoice number | 0 | 2 | 0.0% |
| net | 1 | 1 | 100.0% |
| IVA | 1 | 1 | 100.0% |
| gross | 1 | 2 | 50.0% |
| rate | 1 | 1 | 100.0% |
| all | 5 | 11 | 45.5% |

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
| nota-credito.pdf | miss None | hit 2026-04-15 | hit NC Q2 | flagged empty | flagged empty | hit -10.00 | flagged empty |

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

Tesseract `por+eng` on the first page of each unique PDF, with the QR payload not applied. The counted cells are compared with the production text-layer read.

Raster matched the production counted cells: 11 of 11.

## Follow-ups

- The credit-note fixture prints NIF 501111111. That number fails the check digit, so the extractor leaves the NIF empty. The check stays.
- Vendor lines still keep the first heading (`Fornecedor: Café Lisboa`, `Nota de crédito NC Q2`) instead of the name after Fornecedor.
- The credit note prints no net, IVA, or rate. Those three cells stay flagged.
- On the thermal roll and the photo, the pipeline amounts come from the QR. Tesseract on the roll itself only has the word Talão plus the QR image.
- Month names cover `d de mês de yyyy` and abbreviations such as `set` and `fev.`. Other date layouts are unchanged.
- Crumpled photos and digit mixups are not in this corpus.
