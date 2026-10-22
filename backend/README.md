# Invoflow API

FastAPI backend for Invoflow.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # optional
uvicorn app.main:app --reload --port 8000
```

Health: http://localhost:8000/health

PDF rasterization allows 2 poppler renders in each API process. Started with more than one uvicorn worker, that limit is 2 per worker. `docs/security/poppler.md` tracks CVE-2026-107705.

Default OCR is Tesseract (`por` and `eng`) when those packs are installed, otherwise mock. The mock fallback is logged. Azure is optional and paid.

```bash
sudo apt-get install -y tesseract-ocr tesseract-ocr-por tesseract-ocr-eng poppler-utils
```

`OCR_BACKEND=tesseract` refuses to start without the binary and both language packs. `OCR_BACKEND=auto` uses mock and logs the missing packages. `OCR_BACKEND=mock` chooses mock on purpose. The backend image installs the same three Tesseract packages.
