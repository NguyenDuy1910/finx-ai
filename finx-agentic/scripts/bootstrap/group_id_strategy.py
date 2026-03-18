from __future__ import annotations

_DOMAIN_KEYWORDS: dict[str, list[str]] = {
    "payments": [
        "payment", "transaction", "gl", "general_ledger", "reconcil",
        "napas", "mastercard", "posting", "hub_payment", "hub_load",
        "f_gl", "f_transaction", "f_posting", "asean", "qr", "atm",
        "withdraw", "disbursement",
    ],
    "retail": [
        "card", "notification", "lucky_spin", "gamif", "branch",
        "cobadge", "installment", "dynamic_notification", "saoke",
        "biometric", "avg_deposit", "snap_shot", "vk_card",
    ],
    "loans": [
        "lending", "loan", "credit", "drawdown", "invoice", "cl_",
        "lms", "chovay",
    ],
    "customer360": [
        "customer", "cif", "party", "account_migration", "user_pool",
        "d_customer", "way4_client",
    ],
    "governance": [
        "compliance", "aml", "cft", "kyc", "policy", "access",
        "classification", "hub_load_classification",
    ],
    "metadata": [
        "all_date", "date", "province", "ref_", "reference",
        "dim", "branch_dim", "d_mastercard",
    ],
}

_KW_MAP: dict[str, str] = {
    kw: domain
    for domain, kws in _DOMAIN_KEYWORDS.items()
    for kw in kws
}

_CONFLUENCE_SPACE_MAP: dict[str, str] = {
    "AML": "governance",
    "DAFinX": "metadata",
    "CDCB": "loans",
    "CMS": "retail",
    "EN": "metadata",
    "FINX": "metadata",
}

_FALLBACK_DOMAIN = "metadata"

_CANONICAL_DOMAIN: dict[str, str] = {
    "payment": "payments",
    "transaction": "payments",
    "card": "retail",
    "lending": "loans",
    "loan": "loans",
    "customer": "customer360",
    "compliance": "governance",
    "aml": "governance",
    "reference": "metadata",
    "retail": "retail",
    "payments": "payments",
    "loans": "loans",
    "customer360": "customer360",
    "metadata": "metadata",
    "governance": "governance",
}


def normalize_domain(raw: str | None) -> str:
    if not raw:
        return _FALLBACK_DOMAIN
    low = raw.lower().strip()
    if low in _CANONICAL_DOMAIN:
        return _CANONICAL_DOMAIN[low]
    for kw, domain in _KW_MAP.items():
        if kw in low:
            return domain
    return _FALLBACK_DOMAIN


def infer_domain_from_table_name(table_name: str) -> str:
    low = table_name.lower()
    for kw, domain in _KW_MAP.items():
        if kw in low:
            return domain
    return _FALLBACK_DOMAIN


def get_schema_group_id(domain: str, table_name: str = "") -> str:
    canonical = normalize_domain(domain)
    if canonical == _FALLBACK_DOMAIN and table_name:
        canonical = infer_domain_from_table_name(table_name)
    return f"schema_{canonical}"


def get_confluence_group_id(space: str, item_domain: str = "") -> str:
    if item_domain:
        canonical = normalize_domain(item_domain)
        if canonical != _FALLBACK_DOMAIN:
            return f"confluence_{canonical}"
    space_domain = _CONFLUENCE_SPACE_MAP.get(space)
    if space_domain:
        return f"confluence_{space_domain}"
    return f"confluence_{_FALLBACK_DOMAIN}"
