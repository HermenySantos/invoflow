# Invoflow — e-Fatura Integration Research

> Research conducted: February 2026
> Sources: Official AT documentation (Portal das Financas), AT Integration Manuals V3.0 (October 2025)

---

## 1. Executive Summary

The Portuguese Tax Authority (Autoridade Tributaria e Aduaneira — AT) **does expose official SOAP web services** for the e-Fatura system. As of October 2025 (Manual V3.0), a **new invoice consultation operation** was added that allows querying all invoices associated with a taxpayer's NIF — both as issuer and as buyer. This is directly relevant to Invoflow's core use case.

There are three viable integration paths, ranging from simple file import to full real-time API access.

---

## 2. Official AT Web Services

### 2.1 Invoice Submission Service (Existing)

**Purpose**: Allows certified billing software to submit invoice data to AT in real time.

- **Production endpoint**: `https://servicos.portaldasfinancas.gov.pt:423/fatcorews/ws`
- **Test endpoint**: `https://servicos.portaldasfinancas.gov.pt:723/fatcorews/ws`
- **WSDL**: [Fatcorews.wsdl](https://info.portaldasfinancas.gov.pt/pt/apoio_contribuinte/Faturacao/Fatcorews/Documents/Fatcorews.wsdl)
- **Protocol**: SOAP over HTTPS with WS-Security headers

**Operations available**:

| Operation | Request/Response | Description |
|-----------|-----------------|-------------|
| Register Invoice | RegisterInvoiceRequest / Response | Submit a new commercial document (invoice, credit note, debit note, receipt) |
| Change Invoice Status | ChangeInvoiceStatusRequest / Response | Update status (Normal, Cancelled, Invoiced) |
| Delete Invoice | DeleteInvoiceRequest / Response | Remove a previously submitted document |
| Register Work Document | RegisterWorkRequest / Response | Submit conference/working documents |
| Change Work Status | ChangeWorkStatusRequest / Response | Update working document status |
| Delete Work Document | DeleteWorkRequest / Response | Remove working documents |
| Register Payment | RegisterPaymentRequest / Response | Submit receipts (IVA de Caixa regime) |
| Change Payment Status | ChangePaymentStatusRequest / Response | Update receipt status |
| Delete Payment | DeletePaymentRequest / Response | Remove receipts |

**Relevance to Invoflow**: Low for the MVP. This service is for submitting invoices, not reading them. Invoflow does not issue invoices.

### 2.2 Invoice Consultation Service (NEW — October 2025)

**Purpose**: Allows querying invoices registered in e-Fatura where a NIF appears as either issuer or acquirer (buyer).

- **Production endpoint**: `https://servicos.portaldasfinancas.gov.pt:425/fatshare/ws/fatshareFaturas`
- **Test endpoint**: `https://servicos.portaldasfinancas.gov.pt:725/fatshare/ws/fatshareFaturas`
- **WSDL**: To be published (referenced as "FATSHARE - INVOICES" in the manual, noted as "A disponibilizar em breve" — available soon)
- **Protocol**: SOAP over HTTPS with WS-Security headers

**Operation**:

| Operation | Request/Response | Description |
|-----------|-----------------|-------------|
| Query Invoices | InvoicesRequest / InvoicesResponse | Retrieve invoices where the authenticated NIF is the issuer or acquirer |

**What the response contains** (from the manual, section 2.1.10):
- Invoice number and type (FT, FS, NC, ND, FR)
- Issue date
- Issuer NIF
- Acquirer NIF and country
- Document status (Normal, Cancelled, Invoiced)
- Line summaries by tax rate, including:
  - Tax type (IVA, IS, NS)
  - Tax region (PT, PT-AC for Azores, PT-MA for Madeira)
  - Tax code (RED = reduced, INT = intermediate, NOR = normal, ISE = exempt)
  - Tax percentage
  - Taxable amount
  - Tax exemption codes
- Document totals: TaxPayable, NetTotal, GrossTotal
- Withholding tax details (IRS, IRC, IS)

**Relevance to Invoflow**: **CRITICAL**. This is exactly what Invoflow needs. By authenticating with the user's Portal das Financas credentials, Invoflow could pull all their purchase invoices automatically — complete with VAT breakdowns, tax rates, and totals. This eliminates the need for OCR on any receipt that was registered with a NIF.

**Key quote from the official manual**:

> "Foi introduzida a possibilidade de consulta das faturas registadas no sistema e-Fatura, nas quais o NIF do sujeito passivo figure como transmitente ou adquirente. Este novo desenvolvimento permite integrar, nos softwares de faturacao, funcionalidades para obter, por webservice, os elementos das faturas registadas no sistema e-Fatura, associadas a um determinado sujeito passivo, mediante autenticacao com as credenciais de acesso ao Portal das Financas desse sujeito passivo."

Translation: "The possibility of consulting invoices registered in the e-Fatura system has been introduced, in which the NIF of the taxable person appears as issuer or acquirer. This new development allows integrating, in billing software, functionalities to obtain, by webservice, the elements of invoices registered in the e-Fatura system, associated with a given taxable person, through authentication with Portal das Financas access credentials of that taxable person."

---

## 3. Authentication and Certification Requirements

### 3.1 Software Certification

To access the web services, Invoflow must be registered as a certified software producer with the AT:

1. **Software must be certified** under Portaria 363/2010 and Portaria 340/2013
2. A **software certificate number** is assigned by the AT
3. The certification process involves demonstrating compliance with technical standards

### 3.2 SSL Certificate Process

Each software producer must generate and submit an SSL certificate:

1. Generate a 2048-bit RSA key pair using OpenSSL:
   ```bash
   openssl req -new -subj "/C=PT/ST=District/L=City/O=CompanyName/OU=IT/CN=NIFFFFF/E=email@company.pt" \
     -newkey rsa:2048 -nodes -out NIF.csr -keyout NIF.key
   ```
2. Submit the CSR to AT via email: `asi-cd@at.gov.pt`
3. AT signs the certificate and returns it
4. Certificate is valid for **12 months** (must be renewed annually)
5. No special characters allowed in CSR fields

### 3.3 User Authentication (Per-Request)

Each API call requires SOAP WS-Security headers with:

| Field | Description | Encryption |
|-------|-------------|------------|
| Username | Sub-user ID format: `NIF/subuser_number` (e.g., `555555555/37`) | Plain text |
| Password | Portal das Financas password | AES-128 ECB with per-request symmetric key, then Base64 |
| Nonce | Random 128-bit AES symmetric key (unique per request) | RSA-encrypted with AT's public authentication key, then Base64 |
| Created | UTC timestamp (ISO 8601) | AES-128 ECB with per-request symmetric key, then Base64 |

**Business user setup required**:
- Each business owner must create a sub-user on Portal das Financas
- The sub-user needs the **WFA** permission ("Webservice de comunicacao de dados de faturas")
- Path: Portal das Financas > Cidadaos > Servicos > Autenticacao de Contribuintes > Gestao de Utilizadores

### 3.4 Communication Mode Commitment

Important regulatory detail: Once a business chooses webservice communication for a fiscal year, they must maintain it for the entire year. Exceptions apply only when changing billing software.

---

## 4. SAF-T File Import (Alternative Path)

### What is SAF-T?

SAF-T (Standard Audit File for Tax) is an OECD-standard XML file format used in Portugal for exchanging tax and accounting data. It is mandatory for all VAT-registered entities.

### SAF-T Types in Portugal

| Type | Content | Submission Deadline |
|------|---------|-------------------|
| **SAF-T Billing** | All invoicing and sales data, VAT declarations | By the 5th of each month |
| **SAF-T Accounting** | Full accounting records, items, clients, suppliers, VAT regimes | Annual (obligation postponed to 2028 for fiscal year 2027) |
| **SAF-T Transport** | Transportation document data | Before goods movement begins |

### SAF-T File Structure

- **Format**: XML conforming to SAFT-PT.xsd validation schema
- **Common data**: Products, customers, tax codes
- **Functional data**: Invoices, journal entries, tax summaries
- **Legal basis**: Portaria 321-A/2007, Portaria 31/2019, Decreto-Lei 198/2012

### Relevance to Invoflow

SAF-T import is the **easiest integration path** because:

- No AT certification required
- No API authentication complexity
- The user (or their accountant) already has these files
- Contains structured, validated invoice data with full VAT breakdowns
- XML parsing is straightforward

**Limitation**: SAF-T files are typically generated from the business's own billing software (invoices they issue), not their expense receipts. However, the accounting SAF-T includes purchase records. The accountant's version would have the complete picture.

---

## 5. QR Code Scanning (Additional Path)

### Portuguese Receipt QR Codes

Since January 2022, all Portuguese invoices must include a QR code containing structured invoice data. The official e-Fatura mobile app uses this for invoice registration.

### QR Code Contents

The QR code on Portuguese receipts contains:
- Issuer NIF
- Buyer NIF
- Invoice type and number
- Date
- Tax breakdown (taxable base and tax amount per rate)
- Document totals
- ATCUD (unique document code)
- Hash characters for document integrity

### Relevance to Invoflow

QR code scanning could replace or supplement OCR:
- **Far more accurate** than OCR — structured data, not image recognition
- **Faster** — instant decode vs. API call for OCR processing
- **Cheaper** — no third-party OCR API costs
- **Already standard** — all Portuguese receipts have them since 2022

Invoflow could offer: "Scan the QR code on your receipt" as the primary capture method, with camera OCR as fallback for older or foreign receipts.

---

## 6. The Official e-Fatura Mobile App

### What It Does

- Available on Android (1M+ downloads) and iOS
- Scan QR codes to register invoices
- Classify invoices into IRS deduction categories (health, education, housing, etc.)
- View accumulated personal tax benefits
- Authentication via Chave Movel Digital or Cartao de Cidadao

### What It Does NOT Do

- Predict IVA payable for businesses
- Categorize expenses for business VAT deductibility (Article 21 CIVA)
- Calculate deductible vs. non-deductible VAT
- Export structured data packages for accountants
- Show validation warnings or confidence scores
- Provide period-based IVA dashboards

This gap is Invoflow's opportunity.

---

## 7. Integration Roadmap

### Tier 1: SAF-T File Import (No certification needed)

**Effort**: 1-2 weeks
**Value**: High for accountant workflow

- Build SAF-T XML parser for the billing module
- Accept file upload in Invoflow
- Extract: vendor NIF, invoice amounts, VAT breakdowns, dates
- Map to Invoflow's category system
- Merge with manually scanned receipts for complete picture

**User flow**: User exports SAF-T from Portal das Financas or billing software, uploads to Invoflow.

### Tier 2: QR Code Scanning (No certification needed)

**Effort**: 1-2 weeks
**Value**: High for daily capture workflow

- Implement QR code reader in the mobile capture flow
- Parse the structured data from Portuguese invoice QR codes
- Auto-populate all fields (vendor NIF, amounts, VAT, date)
- Fall back to OCR only when QR code is not available or unreadable

**User flow**: User points camera at receipt QR code instead of taking a photo. Data is captured instantly and accurately.

### Tier 3: e-Fatura API Integration (Requires AT certification)

**Effort**: 2-4 months (including certification process)
**Value**: Transformative — complete automation

Steps:
1. Register Invoflow as a software producer with AT
2. Apply for software certification (Portaria 363/2010)
3. Request SSL certificate and public authentication key from AT
4. Implement SOAP client with WS-Security headers
5. Build the InvoicesRequest consultation flow
6. Test against AT's test environment
7. Apply for production access (adesao ao servico)
8. Deploy and monitor

**User flow**: User connects their Portal das Financas credentials once. Invoflow automatically pulls all their invoices from e-Fatura. Combined with manual receipt scans, the user has a complete expense picture with zero effort.

**This is the moat**. Any competitor would need to go through the same certification process.

---

## 8. Technical Architecture for API Integration

### SOAP Client Requirements

```
Invoflow Backend
    |
    |-- SOAP Client (e.g., zeep for Python, or soap for Node.js)
    |     |-- WS-Security Header Builder
    |     |     |-- AES-128 ECB encryption for password/timestamp
    |     |     |-- RSA encryption for symmetric key (using AT public key)
    |     |     |-- Nonce generation (unique per request)
    |     |
    |     |-- SSL/TLS with AT-signed client certificate
    |     |-- Request builder (InvoicesRequest)
    |     |-- Response parser (InvoicesResponse)
    |
    |-- Credential Vault (encrypted storage for user's WFA sub-user credentials)
    |
    |-- Sync Scheduler (periodic pull of new invoices)
```

### Security Considerations

- User's Portal das Financas credentials must be stored encrypted (AES-256 at rest)
- Credentials are the user's own — they create a sub-user specifically for Invoflow
- The WFA permission is scoped to invoice communication only
- AT's SSL certificate validates the server; Invoflow's client certificate validates the app
- Each request uses a unique symmetric key (Nonce) — no replay attacks possible

### Data Flow

```
AT e-Fatura System
    |
    | (SOAP/HTTPS, port 425)
    |
Invoflow Backend
    |
    |-- Parse InvoicesResponse
    |-- Extract: NIF, dates, amounts, VAT rates, exemption codes
    |-- Auto-categorize using vendor NIF lookup
    |-- Calculate deductible VAT per Article 21 CIVA
    |-- Merge with manually scanned receipts
    |-- Update IVA dashboard
    |
Invoflow Frontend
    |-- Show unified expense view (e-Fatura + manual scans)
    |-- IVA prediction with higher confidence (more complete data)
```

---

## 9. Key AT Contact Information

| Purpose | Contact |
|---------|---------|
| SSL certificates and technical support | asi-cd@at.gov.pt |
| General technical queries | portal-qt@at.gov.pt |
| Software certification | Portal das Financas > Produtores de Software |

---

## 10. Official Documentation Links

- [e-Fatura Webservice Page](https://info.portaldasfinancas.gov.pt/pt/apoio_contribuinte/Faturacao/Fatcorews/Paginas/default.aspx)
- [WSDL Specification (Submission)](https://info.portaldasfinancas.gov.pt/pt/apoio_contribuinte/Faturacao/Fatcorews/Documents/Fatcorews.wsdl)
- [Integration Manual — Specific Aspects (V3.0, Oct 2025)](https://info.portaldasfinancas.gov.pt/pt/apoio_ao_contribuinte/Outras_entidades/Suporte_tecnologico/Webservice/e_Fatura/Documents/Comunicacao_dos_elementos_dos_documentos_de_faturacao.pdf)
- [Integration Manual — General Aspects (V1.0, Oct 2025)](https://info.portaldasfinancas.gov.pt/pt/apoio_ao_contribuinte/Outras_entidades/Suporte_tecnologico/Webservice/e_Fatura/Documents/Comunicacao_dos_elementos_dos_documentos_de_faturacao_aspetos_gerais.pdf)
- [Tax Exemption Codes Table](https://info.portaldasfinancas.gov.pt/pt/apoio_contribuinte/Faturacao/Fatcorews/Documents/Tabela_Codigos_Motivo_Isencao.pdf)
- [System Alignment Document](https://info.portaldasfinancas.gov.pt/pt/apoio_contribuinte/Faturacao/Fatcorews/Documents/Sistema_e_Fatura_alinhamento_de_funcionalidades.pdf)

---

## 11. Summary

| Question | Answer |
|----------|--------|
| Does e-Fatura expose an API? | Yes — official SOAP web services for both submission and consultation |
| Can we read a user's invoices? | Yes — the new consultation service (Oct 2025) returns invoices where the user's NIF is issuer or acquirer |
| What data do we get? | Invoice number, type, date, NIFs, full VAT breakdown by rate, totals, exemption codes, withholding tax |
| What's required? | AT software certification, AT-signed SSL certificate, user creates WFA sub-user |
| How long to implement? | Tier 1 (SAF-T import): 1-2 weeks. Tier 2 (QR codes): 1-2 weeks. Tier 3 (full API): 2-4 months |
| Is it worth it? | Tier 3 is transformative — it turns Invoflow from "useful tool" into "essential infrastructure" and creates a competitive moat |
