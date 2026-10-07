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

Default OCR is Tesseract when the binary is installed, otherwise mock. Azure is optional and paid.
