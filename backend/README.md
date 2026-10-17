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

Default OCR is Tesseract when the binary is installed, otherwise mock. Azure is optional and paid.
