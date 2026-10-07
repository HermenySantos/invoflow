# Invoflow

**Simple invoice/receipt management to predict IVA and package documents for the accountant (Portugal)**

---

## The Problem

A small business owner in Portugal collects dozens of paper receipts every month. They shove them in a drawer, a shoebox, or a folder. Eventually they hand the pile to their accountant — who then tells them "you owe X in IVA" sometimes just 1 day before the AT deadline. The owner scrambles to find the cash. If a receipt is lost, the deduction is gone.

## The Solution

Invoflow is not an accounting app. It is a capture-and-predict tool that sits between the business owner and their accountant.

### 1. Capture

The owner snaps photos of receipts as they come in using their phone camera (mobile-first PWA). No more accumulating paper. No more trips to the accountant's office carrying folders.

### 2. Extract and Organize

OCR automatically pulls out vendor name, NIF, date, amounts, and VAT. Documents are stored immutably in the cloud. The original file is always the source of truth; extracted data is editable metadata layered on top. Everything is searchable by vendor, date, amount, or category.

### 3. Predict

Based on the categorized expenses and their VAT deductibility rules (Article 21 of the Portuguese VAT Code — CIVA), the system shows an **estimated IVA payable** for the current period — weeks before the deadline, not hours.

The owner knows "I will need roughly 500 EUR by the 20th" and can plan cash accordingly.

Confidence flags and validation warnings make it clear this is an estimate, not a tax return. The system highlights uncertainty — missing fields, low OCR confidence, uncategorized items, potential duplicates — so nothing slips through unnoticed.

### 4. Package

When it is time for the accountant, the owner exports a clean ZIP archive containing:

- All original receipt files organized by date
- A summary CSV with vendor, amounts, VAT breakdown, expense category, IRS sector, and deductible percentages
- A summary PDF with totals and document listing

The accountant receives a structured, traceable package instead of a shoebox.

---

## The Value

- **Owner saves time** — no trips to deliver paper, no manual sorting
- **Owner avoids surprise** — IVA estimate visible at least 7 days before the payment deadline
- **Accountant saves time** — structured, consistent input instead of chaos
- **Nothing is lost** — cloud storage with immutable originals and full audit trail

---

## What Invoflow Is NOT

- **Not a tax filing tool** — it does not submit anything to Autoridade Tributaria
- **Not an invoicing or sales tool** — VAT on sales is manual input; this is about expenses
- **Not authoritative** — positioned as estimation and organization; the accountant has the final say

---

## Target Users

**Primary: Business Owner / Manager**
- Captures lots of paper receipts on iPhone or Android
- Wants predictable IVA payable and less paperwork

**Secondary: Accountant (external)**
- Receives exports and summary
- Wants consistent structure, originals, and correct totals

---

## Key Features (MVP)

- Mobile-first PWA with camera capture
- OCR extraction via Azure Document Intelligence
- Auto-categorization into expense categories and IRS deduction sectors
- Accurate Portuguese VAT deductibility rules (Article 21 CIVA)
- IVA estimation dashboard with monthly and quarterly views
- Manual VAT on sales input
- Validation system (missing fields, low confidence, VAT inconsistencies, duplicates)
- Immutable audit trail (what came from OCR vs what was edited by the user)
- Accountant-ready export package (ZIP with originals + CSV + PDF)
- Payment deadline countdown with cash reminder
- Authentication and per-user data isolation
