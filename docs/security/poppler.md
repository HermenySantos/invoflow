# Poppler

## CVE-2026-107705

Poppler 0.42.0 through 26.10.0 has a stack buffer overflow in `Decrypt::revision6Hash()` when it opens an AESV3/R6 encrypted PDF. The API image pins `poppler-utils=25.03.0-5+deb13u4` from Debian trixie. The [Debian tracker](https://security-tracker.debian.org/tracker/CVE-2026-107705) still lists that package as vulnerable. Upstream fix is commit `2703be11769c1f86f4d0dc3b276ec94bba5ac6d3` ([merge request 2398](https://gitlab.freedesktop.org/poppler/poppler/-/merge_requests/2398)).

Mitigation in this build: an encrypted PDF never reaches poppler. `_pdf_allowed` rejects it when pypdf reports `is_encrypted`, and `POST /api/documents` answers 415.

Upgrade trigger: when Debian publishes a `poppler-utils` that includes that commit, replace the pin in `backend/Dockerfile` with the fixed package version. Keep the 415. The pin stays on `25.03.0-5+deb13u4` until that package exists.

## Rasterizer concurrency

`_PDF_RASTER_SLOTS` in `backend/app/services/ocr.py` is a `threading.Semaphore(2)` inside one API process. It does not span processes. The image starts uvicorn with one worker. If it is started with `--workers N`, poppler can run 2 × N renders at once.

A page is rasterized only when its shorter side is at most 2000 pt and the image at the chosen dpi stays within 25 megapixels. A page that is over 2000 pt on both sides is marked `needs_review` and its QR is skipped. A long, narrow receipt, such as 80 mm by 3000 pt, stays under the pixel budget and is rasterized.
