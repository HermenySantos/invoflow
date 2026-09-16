# FaturaFlow

Product name: **FaturaFlow**. Repository name remains `invoflow`.

Upload a Portuguese receipt or invoice → IVA estimate → accountant pack.

This is a personal MIT product. It does not include Dorier / employer IP.

The public landing at `/` follows the Eggbot FaturaFlow landing spec (CVO integrate). Do not replace it with a second marketing design.

## One path: Docker Compose

Needs Docker Desktop or Engine + Compose.

```bash
git clone https://github.com/HermenySantos/invoflow.git
cd invoflow
docker compose up --build
```

Then open:

- App / landing: http://localhost:3000
- Upload (live demo): http://localhost:3000/upload
- API health: http://localhost:8000/health

Sign in with any email (mock auth). No Azure, Clerk, or R2 keys.

Stop with `Ctrl+C`, then `docker compose down`.

## Path without Docker (pip + npm)

Needs Python 3.11+ and Node 18+. Tesseract is optional.

```bash
# API
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
# optional: cp .env.example .env
uvicorn app.main:app --reload --port 8000
```

In another terminal:

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:3000

This path uses SQLite (`backend/invoflow.db`) and local files (`backend/mock_storage/`). If Tesseract is not installed, OCR falls back to mock data.

Optional system OCR (Debian/Ubuntu):

```bash
sudo apt-get install -y tesseract-ocr tesseract-ocr-por tesseract-ocr-eng
```

Poetry is optional: `cd backend && poetry install && poetry run uvicorn app.main:app --reload --port 8000`.

## What is real vs mock

| Piece | Default | Paid optional |
| --- | --- | --- |
| Auth | Mock (any email) | Clerk |
| Storage | Local `mock_storage/` | Cloudflare R2 (+ boto3) |
| OCR | **Tesseract** if installed, else mock | Azure Document Intelligence |
| LLM polish | Off | Local Ollama (`OLLAMA_BASE_URL`) |
| Database | SQLite (no-Docker) or Compose Postgres | Neon / any Postgres |
| Export ZIP | Real (CSV + PDF + originals when on disk) | — |

IVA is an **estimate for review**, not a filing. Sales VAT is not entered in this version.

## Landing (Eggbot spec)

`/` is the FaturaFlow marketing page: PT first, boring SMB tone, single scroll, tokens from the Eggbot spec. Primary CTA goes to `/upload` (live in this repo). There is no waitlist, no fake counts, no “AI-powered” headline.

`/privacy` is a stub. CVO: replace with real legal copy when hosting.

## OCR backends

`OCR_BACKEND=auto|tesseract|mock|azure`

- `auto` (default): Tesseract when the binary is present, otherwise mock.
- `tesseract`: open-source OCR + Portuguese field extractor (NIF, dates, IVA 6/13/23).
- `mock`: demo vendors/amounts, no image reading.
- `azure`: optional paid Document Intelligence. Ignored unless endpoint + key are set.

Field extraction ideas (schema after OCR text) were adapted from the TaxHacker OSS pipeline. No proprietary blobs were copied.

## Project layout

```
invoflow/
├── backend/          FastAPI + SQLAlchemy
├── frontend/         Next.js 14 (landing + app)
└── docker-compose.yml
```

App routes: `/upload` (also `/scan`), `/receipts`, `/summary`.

## Tests

```bash
cd backend
source .venv/bin/activate
pytest
```

## License

MIT
