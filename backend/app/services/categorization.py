"""
Auto-categorization service for receipts.
Maps vendor names and NIFs to business expense categories and IRS deduction sectors.
"""

import re
from typing import Optional, Tuple

# ── Business Expense Categories ──
EXPENSE_CATEGORIES = {
    "office": "Escritório",
    "travel": "Transporte",
    "utilities": "Serviços",
    "food": "Alimentação",
    "fuel": "Combustível",
    "health": "Saúde",
    "education": "Educação",
    "housing": "Habitação",
    "marketing": "Publicidade",
    "services": "Serviços Prof.",
    "equipment": "Equipamento",
    "other": "Outro",
}

# ── IRS Deduction Sectors (matching AT e-fatura categories) ──
IRS_SECTORS = {
    "saude": "Saúde",
    "educacao": "Educação",
    "habitacao": "Habitação",
    "lares": "Lares",
    "reparacao_automoveis": "Rep. Automóveis",
    "reparacao_motos": "Rep. Motociclos",
    "restauracao_alojamento": "Restauração",
    "cabeleireiros": "Cabeleireiros",
    "veterinarios": "Veterinários",
    "ginasios": "Ginásios",
    "geral": "Despesas Gerais",
    "isento": "Isento",
}


# ── Vendor name patterns → (expense_category, irs_sector) ──
# Matched via case-insensitive substring.
_VENDOR_NAME_MAP: list[Tuple[str, str, str]] = [
    # Supermarkets & grocery
    ("continente", "food", "geral"),
    ("pingo doce", "food", "geral"),
    ("lidl", "food", "geral"),
    ("aldi", "food", "geral"),
    ("minipreço", "food", "geral"),
    ("minipreco", "food", "geral"),
    ("intermarché", "food", "geral"),
    ("intermarche", "food", "geral"),
    ("auchan", "food", "geral"),
    ("mercadona", "food", "geral"),
    ("jumbo", "food", "geral"),

    # Restaurants & cafés
    ("restaurante", "food", "restauracao_alojamento"),
    ("café", "food", "restauracao_alojamento"),
    ("cafe", "food", "restauracao_alojamento"),
    ("pastelaria", "food", "restauracao_alojamento"),
    ("pizzaria", "food", "restauracao_alojamento"),
    ("churrasqueira", "food", "restauracao_alojamento"),
    ("cervejaria", "food", "restauracao_alojamento"),
    ("marisqueira", "food", "restauracao_alojamento"),
    ("padaria", "food", "restauracao_alojamento"),
    ("snack", "food", "restauracao_alojamento"),
    ("mcdonald", "food", "restauracao_alojamento"),
    ("burger king", "food", "restauracao_alojamento"),
    ("telepizza", "food", "restauracao_alojamento"),
    ("dominos", "food", "restauracao_alojamento"),
    ("pizza hut", "food", "restauracao_alojamento"),
    ("kfc", "food", "restauracao_alojamento"),
    ("subway", "food", "restauracao_alojamento"),
    ("starbucks", "food", "restauracao_alojamento"),
    ("pans company", "food", "restauracao_alojamento"),
    ("taberna", "food", "restauracao_alojamento"),
    ("tasca", "food", "restauracao_alojamento"),

    # Hotels & accommodation
    ("hotel", "travel", "restauracao_alojamento"),
    ("hostel", "travel", "restauracao_alojamento"),
    ("pousada", "travel", "restauracao_alojamento"),
    ("airbnb", "travel", "restauracao_alojamento"),
    ("booking", "travel", "restauracao_alojamento"),
    ("alojamento", "travel", "restauracao_alojamento"),

    # Fuel
    ("galp", "fuel", "geral"),
    ("bp ", "fuel", "geral"),
    ("repsol", "fuel", "geral"),
    ("cepsa", "fuel", "geral"),
    ("prio", "fuel", "geral"),
    ("gasolina", "fuel", "geral"),
    ("combustível", "fuel", "geral"),
    ("combustivel", "fuel", "geral"),
    ("posto de abastecimento", "fuel", "geral"),

    # Transport
    ("uber", "travel", "geral"),
    ("bolt", "travel", "geral"),
    ("freenow", "travel", "geral"),
    ("free now", "travel", "geral"),
    ("taxi", "travel", "geral"),
    ("cp ", "travel", "geral"),
    ("metro ", "travel", "geral"),
    ("carris", "travel", "geral"),
    ("viva viagem", "travel", "geral"),
    ("tap ", "travel", "geral"),
    ("ryanair", "travel", "geral"),
    ("easyjet", "travel", "geral"),

    # Utilities & telecom
    ("edp", "utilities", "geral"),
    ("endesa", "utilities", "geral"),
    ("iberdrola", "utilities", "geral"),
    ("galp energia", "utilities", "geral"),
    ("e-redes", "utilities", "geral"),
    ("nos ", "utilities", "geral"),
    ("nos comunicações", "utilities", "geral"),
    ("meo", "utilities", "geral"),
    ("vodafone", "utilities", "geral"),
    ("nowo", "utilities", "geral"),
    ("epal", "utilities", "geral"),
    ("água", "utilities", "geral"),
    ("agua", "utilities", "geral"),

    # Electronics & equipment
    ("worten", "equipment", "geral"),
    ("fnac", "equipment", "geral"),
    ("media markt", "equipment", "geral"),
    ("apple", "equipment", "geral"),
    ("pc diga", "equipment", "geral"),

    # Health & pharmacy
    ("farmácia", "health", "saude"),
    ("farmacia", "health", "saude"),
    ("hospital", "health", "saude"),
    ("clínica", "health", "saude"),
    ("clinica", "health", "saude"),
    ("centro de saúde", "health", "saude"),
    ("centro de saude", "health", "saude"),
    ("dentista", "health", "saude"),
    ("médico", "health", "saude"),
    ("medico", "health", "saude"),
    ("laboratório", "health", "saude"),
    ("laboratorio", "health", "saude"),
    ("ótica", "health", "saude"),
    ("otica", "health", "saude"),
    ("wells", "health", "saude"),

    # Education
    ("escola", "education", "educacao"),
    ("universidade", "education", "educacao"),
    ("faculdade", "education", "educacao"),
    ("instituto", "education", "educacao"),
    ("colégio", "education", "educacao"),
    ("colegio", "education", "educacao"),
    ("livraria", "education", "educacao"),
    ("bertrand", "education", "educacao"),
    ("fnac livros", "education", "educacao"),
    ("papelaria", "education", "educacao"),

    # Hairdressers & beauty
    ("cabeleireiro", "services", "cabeleireiros"),
    ("barbeiro", "services", "cabeleireiros"),
    ("salão", "services", "cabeleireiros"),
    ("salao", "services", "cabeleireiros"),
    ("beauty", "services", "cabeleireiros"),

    # Veterinary
    ("veterinário", "health", "veterinarios"),
    ("veterinario", "health", "veterinarios"),
    ("pet ", "health", "veterinarios"),

    # Gym & fitness
    ("ginásio", "health", "ginasios"),
    ("ginasio", "health", "ginasios"),
    ("fitness", "health", "ginasios"),
    ("gym", "health", "ginasios"),
    ("solinca", "health", "ginasios"),
    ("holmes place", "health", "ginasios"),

    # Vehicle repair
    ("oficina", "services", "reparacao_automoveis"),
    ("auto ", "services", "reparacao_automoveis"),
    ("mecânico", "services", "reparacao_automoveis"),
    ("mecanico", "services", "reparacao_automoveis"),
    ("norauto", "services", "reparacao_automoveis"),
    ("midas", "services", "reparacao_automoveis"),
    ("feu vert", "services", "reparacao_automoveis"),

    # Housing
    ("imobiliária", "housing", "habitacao"),
    ("imobiliaria", "housing", "habitacao"),
    ("renda", "housing", "habitacao"),
    ("condomínio", "housing", "habitacao"),
    ("condominio", "housing", "habitacao"),

    # Office supplies
    ("staples", "office", "geral"),
    ("note", "office", "geral"),

    # Marketing
    ("google ads", "marketing", "geral"),
    ("facebook ads", "marketing", "geral"),
    ("meta ads", "marketing", "geral"),
]

# ── NIF prefix map (first 3 digits of known chains) ──
_NIF_MAP: dict[str, Tuple[str, str]] = {
    "500100144": ("food", "geral"),       # Continente / Sonae
    "500829993": ("food", "geral"),       # Pingo Doce / Jerónimo Martins
    "502428880": ("equipment", "geral"),  # Worten
    "504499777": ("fuel", "geral"),       # GALP Energia
    "504448064": ("utilities", "geral"),  # NOS Comunicações
    "503504564": ("utilities", "geral"),  # EDP Comercial
    "502793208": ("utilities", "geral"),  # MEO / Altice
    "501507930": ("utilities", "geral"),  # Vodafone Portugal
    "500273066": ("travel", "geral"),     # TAP
    "500252100": ("food", "geral"),       # Auchan
}


# Longest patterns first so "galp energia" wins over "galp"; whole words only
# so "renda" doesn't match "merenda".
_VENDOR_PATTERNS = [
    (re.compile(rf"\b{re.escape(pattern)}\b"), expense_cat, irs_sector)
    for pattern, expense_cat, irs_sector in sorted(
        _VENDOR_NAME_MAP, key=lambda entry: len(entry[0]), reverse=True
    )
]


def categorize_document(
    vendor_name: Optional[str],
    vendor_nif: Optional[str],
) -> Tuple[str, str]:
    """
    Auto-categorize a document based on vendor name and NIF.
    
    Returns (expense_category, irs_sector).
    Falls back to ("other", "geral") when no match is found.
    """
    # 1. Try NIF exact match first (most reliable)
    if vendor_nif and vendor_nif in _NIF_MAP:
        return _NIF_MAP[vendor_nif]
    
    # 2. Try vendor name substring match
    if vendor_name:
        name_lower = vendor_name.lower().strip()
        for regex, expense_cat, irs_sector in _VENDOR_PATTERNS:
            if regex.search(name_lower):
                return (expense_cat, irs_sector)
    
    # 3. Fallback
    return ("other", "geral")


# ── VAT deductibility percentages (for business IVA calculation) ──
# Based on Article 21 of the Portuguese VAT Code (CIVA).
# Controls how much of the VAT on each expense category can be reclaimed.
# 100 = fully deductible, 50 = half, 0 = excluded from deduction.
#
# References:
#   Art. 21(1)(a) – Vehicles: tourism vehicles excluded (purchase, rental, repair)
#   Art. 21(1)(b) – Fuel: gasoline 0%; diesel/GPL/GN/biofuels 50%
#   Art. 21(1)(c) – Transport & business travel (incl. tolls): excluded
#   Art. 21(1)(d) – Accommodation, food, beverages, tobacco: excluded
#   Art. 21(1)(e) – Entertainment & luxury expenses: excluded
#   Art. 21(2)(d) – Congress/fair organizer: 50% for transport/accommodation/food
#   Art. 21(2)(e) – Congress/fair participant: 25% for transport/accommodation/food
#   Art. 21(2)(f) – Electric/hybrid plug-in vehicles: deductible (up to cost limits)
#   Art. 21(2)(h) – Electricity for electric/hybrid vehicles: deductible
#
EXPENSE_DEDUCTIBLE_PCT: dict[str, int] = {
    "office": 100,      # Office supplies — fully deductible (Art. 19/20 CIVA)
    "travel": 0,        # Art. 21(1)(c): transport & business travel EXCLUDED
    "utilities": 100,   # Electricity, water, telecom — fully deductible
    "food": 0,          # Art. 21(1)(d): food, beverages, meals EXCLUDED
    "fuel": 50,         # Art. 21(1)(b): diesel/GPL/GN/biofuels at 50%; gasoline 0%
    "health": 0,        # Personal/exempt — not deductible for IVA
    "education": 0,     # Personal expense — not deductible for IVA
    "housing": 0,       # Residential rent is VAT-exempt; commercial rent → recategorize to office
    "marketing": 100,   # Advertising/publicity — fully deductible
    "services": 100,    # Professional services — fully deductible (Note: vehicle repair for passenger cars excluded per Art. 21(1)(a))
    "equipment": 100,   # Business equipment — fully deductible (Note: passenger vehicles excluded per Art. 21(1)(a))
    "other": 0,         # Unknown — conservative until categorized
}


def get_deductible_pct(expense_category: str | None) -> int:
    """Return the VAT deductibility percentage for a category (0-100)."""
    if not expense_category:
        return 0
    return EXPENSE_DEDUCTIBLE_PCT.get(expense_category, 0)


def get_expense_category_label(category: str) -> str:
    """Get the Portuguese display label for an expense category."""
    return EXPENSE_CATEGORIES.get(category, "Outro")


def get_irs_sector_label(sector: str) -> str:
    """Get the Portuguese display label for an IRS sector."""
    return IRS_SECTORS.get(sector, "Despesas Gerais")
