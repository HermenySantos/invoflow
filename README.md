# InvoFlow

Simple invoice and receipt management for Portuguese small businesses.

## Overview

InvoFlow helps business owners:
- **Capture** receipts via mobile camera or file upload
- **Extract** key data automatically using OCR
- **Track** estimated IVA (VAT) in real-time
- **Export** accountant-ready packages

## Quick Start

### Prerequisites

- Docker & Docker Compose
- Node.js 18+
- Python 3.11+
- Poetry (Python package manager)

### 1. Start the Database

```bash
docker-compose up -d
```

### 2. Start the Backend

```bash
cd backend
poetry install
poetry run uvicorn app.main:app --reload --port 8000
```

### 3. Start the Frontend

```bash
cd frontend
npm install
npm run dev
```

### 4. Open the App

Visit [http://localhost:3000](http://localhost:3000)

## Project Structure

```
invoflow/
├── backend/          # FastAPI Python backend
│   ├── app/
│   │   ├── api/      # API endpoints
│   │   ├── core/     # Config, auth, database
│   │   ├── models/   # SQLAlchemy models
│   │   ├── schemas/  # Pydantic schemas
│   │   └── services/ # Business logic (OCR, storage, export)
│   └── alembic/      # Database migrations
├── frontend/         # Next.js React frontend
│   ├── app/          # Pages (App Router)
│   ├── components/   # React components
│   └── lib/          # Utilities, API client
└── docker-compose.yml
```

## Development Mode

The app runs in **mock mode** by default:

- **Auth**: No real authentication needed - just enter any email
- **Storage**: Files stored locally in `backend/mock_storage/`
- **OCR**: Returns realistic mock data (Portuguese vendors, amounts, dates)

This allows you to test the full flow without external service credentials.

## Configuration

### Backend Environment Variables

Copy `backend/.env.example` to `backend/.env`:

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_URL` | PostgreSQL connection string | Local Docker DB |
| `AUTH_MOCK_MODE` | Use mock authentication | `true` |
| `STORAGE_MOCK_MODE` | Use local file storage | `true` |
| `OCR_MOCK_MODE` | Use mock OCR data | `true` |

### Enabling Real Services

To use real external services, set the mock mode to `false` and provide credentials:

**Clerk (Authentication)**
```env
AUTH_MOCK_MODE=false
CLERK_SECRET_KEY=sk_...
CLERK_PUBLISHABLE_KEY=pk_...
CLERK_JWKS_URL=https://...clerk.accounts.dev/.well-known/jwks.json
```

**Cloudflare R2 (Storage)**
```env
STORAGE_MOCK_MODE=false
R2_ACCOUNT_ID=...
R2_ACCESS_KEY_ID=...
R2_SECRET_ACCESS_KEY=...
R2_BUCKET_NAME=invoflow-documents
```

**Azure Document Intelligence (OCR)**
```env
OCR_MOCK_MODE=false
AZURE_DOC_ENDPOINT=https://....cognitiveservices.azure.com/
AZURE_DOC_KEY=...
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/documents/upload-url` | Get presigned upload URL |
| `POST` | `/api/documents` | Create document + trigger OCR |
| `GET` | `/api/documents` | List all documents |
| `GET` | `/api/documents/{id}` | Get document details |
| `PATCH` | `/api/documents/{id}` | Update document fields |
| `DELETE` | `/api/documents/{id}` | Delete document |
| `GET` | `/api/summary` | Get IVA summary for period |
| `GET` | `/api/export` | Download export ZIP |

## Tech Stack

**Backend**
- FastAPI (Python)
- PostgreSQL + SQLAlchemy
- Azure Document Intelligence (OCR)
- Cloudflare R2 (Storage)

**Frontend**
- Next.js 14 (React)
- Tailwind CSS
- PWA (Progressive Web App)
- Clerk (Authentication)

## License

MIT
