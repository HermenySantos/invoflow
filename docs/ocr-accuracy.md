# OCR corpus accuracy

Synthetic fixtures only. Café Lisboa, the credit note, the thermal roll, and the photo use made-up names and numbers. Nothing here is a taxpayer record.

Scored fields are NIF, date, invoice number, net, IVA, gross, and rate. An empty cell is a hit when the fixture prints nothing for that field. Net 10.00 and rate 23.00 on the café invoice are implied from the printed total and IVA.

## Before, production path

Same six documents, before the month-name, series-prefix, and credit-sign changes. The four PDFs were scored from the text layer. The thermal roll and the photo were scored from the QR pipeline.

| field | hits | docs | accuracy |
| --- | --- | --- | --- |
| NIF | 4 | 6 | 66.7% |
| date | 2 | 6 | 33.3% |
| invoice number | 2 | 6 | 33.3% |
| net | 6 | 6 | 100.0% |
| IVA | 6 | 6 | 100.0% |
| gross | 4 | 6 | 66.7% |
| rate | 6 | 6 | 100.0% |
| all | 30 | 42 | 71.4% |

## Before, Tesseract on the four PDF rasters

Same poppler render and `por+eng` read, before those extractor changes. The four PDFs missed the same date, invoice number, and credit sign as the text layer. The thermal roll and the photo were not in this pass.

| field | hits | docs | accuracy |
| --- | --- | --- | --- |
| NIF | 2 | 4 | 50.0% |
| date | 0 | 4 | 0.0% |
| invoice number | 0 | 4 | 0.0% |
| net | 4 | 4 | 100.0% |
| IVA | 4 | 4 | 100.0% |
| gross | 2 | 4 | 50.0% |
| rate | 4 | 4 | 100.0% |
| all | 16 | 28 | 57.1% |

## After, production path

What `OCRService.process_document` returns with `OCR_BACKEND=tesseract`. Text PDFs use the text layer. The thermal roll and the photo use the raster plus the QR payload.

| field | hits | docs | accuracy |
| --- | --- | --- | --- |
| NIF | 4 | 6 | 66.7% |
| date | 6 | 6 | 100.0% |
| invoice number | 6 | 6 | 100.0% |
| net | 6 | 6 | 100.0% |
| IVA | 6 | 6 | 100.0% |
| gross | 6 | 6 | 100.0% |
| rate | 6 | 6 | 100.0% |
| all | 40 | 42 | 95.2% |

| document | path | NIF | date | invoice number | net | IVA | gross | rate |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| fatura-cafe-lisboa.pdf | pipeline | hit 503504564 | hit 2026-03-31 | hit FT A/12 | hit 10.00 | hit 2.30 | hit 12.30 | hit 23.00 |
| fatura-cafe-lisboa.qpdf.pdf | pipeline | hit 503504564 | hit 2026-03-31 | hit FT A/12 | hit 10.00 | hit 2.30 | hit 12.30 | hit 23.00 |
| nota-credito.pdf | pipeline | miss empty | hit 2026-04-15 | hit NC Q2 | hit empty | hit empty | hit -10.00 | hit empty |
| nota-credito.qpdf.pdf | pipeline | miss empty | hit 2026-04-15 | hit NC Q2 | hit empty | hit empty | hit -10.00 | hit empty |
| thermal-80mm.pdf | pipeline | hit 503504564 | hit 2026-09-15 | hit FT A/12 | hit 30.00 | hit 5.20 | hit 35.20 | hit empty |
| fatura-photo.png | pipeline | hit 503504564 | hit 2026-09-15 | hit FT A/12 | hit 30.00 | hit 5.20 | hit 35.20 | hit empty |

## After, Tesseract on the raster

First page rendered with the same poppler cap as the app, then Tesseract `por+eng`, then the field extractor. The QR payload is not applied, so this table is the glyph read.

Four LibreOffice PDFs only, comparable to the before raster table.

| field | hits | docs | accuracy |
| --- | --- | --- | --- |
| NIF | 2 | 4 | 50.0% |
| date | 4 | 4 | 100.0% |
| invoice number | 4 | 4 | 100.0% |
| net | 4 | 4 | 100.0% |
| IVA | 4 | 4 | 100.0% |
| gross | 4 | 4 | 100.0% |
| rate | 4 | 4 | 100.0% |
| all | 26 | 28 | 92.9% |

All six documents. The thermal roll and the photo add misses here because the QR is not applied.

| field | hits | docs | accuracy |
| --- | --- | --- | --- |
| NIF | 2 | 6 | 33.3% |
| date | 4 | 6 | 66.7% |
| invoice number | 4 | 6 | 66.7% |
| net | 4 | 6 | 66.7% |
| IVA | 4 | 6 | 66.7% |
| gross | 4 | 6 | 66.7% |
| rate | 6 | 6 | 100.0% |
| all | 28 | 42 | 66.7% |

| document | path | NIF | date | invoice number | net | IVA | gross | rate |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| fatura-cafe-lisboa.pdf | tesseract | hit 503504564 | hit 2026-03-31 | hit FT A/12 | hit 10.00 | hit 2.30 | hit 12.30 | hit 23.00 |
| fatura-cafe-lisboa.qpdf.pdf | tesseract | hit 503504564 | hit 2026-03-31 | hit FT A/12 | hit 10.00 | hit 2.30 | hit 12.30 | hit 23.00 |
| nota-credito.pdf | tesseract | miss empty | hit 2026-04-15 | hit NC Q2 | hit empty | hit empty | hit -10.00 | hit empty |
| nota-credito.qpdf.pdf | tesseract | miss empty | hit 2026-04-15 | hit NC Q2 | hit empty | hit empty | hit -10.00 | hit empty |
| thermal-80mm.pdf | tesseract | miss empty | miss empty | miss empty | miss empty | miss empty | miss empty | hit empty |
| fatura-photo.png | tesseract | miss empty | miss empty | miss empty | miss empty | miss empty | miss empty | hit empty |

## Follow-ups

- The credit-note fixture prints NIF 501111111. That number fails the check digit, so the extractor leaves the NIF empty. The check stays.
- Vendor lines still keep the first heading (`Fornecedor: Café Lisboa`, `Nota de crédito NC Q2`) instead of the name after Fornecedor.
- The credit note prints no net, IVA, or rate.
- On the thermal roll and the photo, the scored amounts come from the QR. Tesseract on the roll itself only has the word Talão plus the QR image.
- Month names cover `d de mês de yyyy`, with or without the accent on março. Other date layouts are unchanged.
- Crumpled photos and digit mixups are not in this corpus.
