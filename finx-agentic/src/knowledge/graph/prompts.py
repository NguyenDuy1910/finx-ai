from __future__ import annotations

# ── Delimiters (LightRAG convention) ──────────────────────────────────────────

TUPLE_DELIMITER = "<|#|>"
COMPLETION_DELIMITER = "<|COMPLETE|>"

# ── Entity types available to the LLM ─────────────────────────────────────────

ENTITY_TYPES = [
    "Table", "Dataset", "Column", "BusinessTerm",
    "Metric", "Dimension", "SourceAuthority", "UserRole", "Concept",
]

EDGE_TYPES = [
    "BELONGS_TO", "HAS_COLUMN", "BACKED_BY", "REFERS_TO",
    "ALIAS_OF", "RELATED_TO", "DEFINED_AS", "OWNED_BY",
    "JOINS_WITH", "PART_OF",
]

# ── System prompt: extraction ─────────────────────────────────────────────────

_EXTRACTION_EXAMPLES = """\
<Input Text>
=== Table: DM_DEPOSIT_TXN ===
Database: prod_bronze_zone
Dataset: deposits
Domain: retail_banking
Description: Bảng giao dịch tiền gửi lưu chi tiết giao dịch gửi và rút.
AI analysis: Dùng TXN_ID làm khóa chính, join với DM_CUSTOMER qua CUSTOMER_ID.
Synonyms: deposit transactions, giao dịch tiền gửi
Tags: retail_banking, transactional, PII
Partition keys: year, month, day
Table relationships:
  - BELONGS_TO: DM_DEPOSIT_TXN → deposits
  - JOINS_TO: DM_DEPOSIT_TXN → DM_CUSTOMER
Columns (5 total):
  - TXN_ID (string) [PK]: Mã giao dịch tiền gửi duy nhất
  - AMOUNT (decimal) [nullable]: Số tiền giao dịch (VND/ngoại tệ)
  - CUSTOMER_ID (string) [nullable]: Mã khách hàng thực hiện giao dịch (also: CIF, mã KH)
  - TXN_DATE (date) [nullable]: Ngày thực hiện giao dịch
  - BRANCH_ID (string) [nullable]: Mã chi nhánh thực hiện giao dịch

<Output>
entity{td}DM_DEPOSIT_TXN{td}Table{td}Bảng giao dịch tiền gửi (deposit transaction table) — lưu chi tiết giao dịch gửi và rút tiền, thuộc domain retail_banking, dataset deposits
entity{td}DEPOSITS{td}Dataset{td}Dataset chứa các bảng giao dịch tiền gửi (deposit-related tables) thuộc hệ thống retail banking
entity{td}RETAIL_BANKING{td}Concept{td}Domain nghiệp vụ ngân hàng bán lẻ (retail banking), quản lý tài khoản và giao dịch cá nhân
entity{td}DM_DEPOSIT_TXN.TXN_ID{td}Column{td}Mã giao dịch tiền gửi duy nhất (deposit transaction ID) — khóa chính (PK) của bảng DM_DEPOSIT_TXN
entity{td}DM_DEPOSIT_TXN.AMOUNT{td}Column{td}Số tiền giao dịch tiền gửi (VND hoặc ngoại tệ)
entity{td}DM_DEPOSIT_TXN.CUSTOMER_ID{td}Column{td}Mã khách hàng (CIF) thực hiện giao dịch — dùng để join với bảng DM_CUSTOMER
entity{td}DM_DEPOSIT_TXN.TXN_DATE{td}Column{td}Ngày thực hiện giao dịch tiền gửi
entity{td}DM_DEPOSIT_TXN.BRANCH_ID{td}Column{td}Mã chi nhánh nơi thực hiện giao dịch — dùng để join với bảng chi nhánh
entity{td}GIAO DỊCH TIỀN GỬI{td}BusinessTerm{td}Thuật ngữ nghiệp vụ chỉ giao dịch liên quan đến tiền gửi ngân hàng (deposit transaction)
entity{td}DM_CUSTOMER{td}Table{td}Bảng khách hàng được tham chiếu từ DM_DEPOSIT_TXN qua cột CUSTOMER_ID
relation{td}DM_DEPOSIT_TXN{td}DEPOSITS{td}belongs_to{td}Bảng DM_DEPOSIT_TXN thuộc dataset DEPOSITS
relation{td}DM_DEPOSIT_TXN{td}DM_DEPOSIT_TXN.TXN_ID{td}has_column{td}DM_DEPOSIT_TXN có cột TXN_ID là khóa chính
relation{td}DM_DEPOSIT_TXN{td}DM_DEPOSIT_TXN.AMOUNT{td}has_column{td}DM_DEPOSIT_TXN có cột AMOUNT lưu số tiền giao dịch
relation{td}DM_DEPOSIT_TXN{td}DM_DEPOSIT_TXN.CUSTOMER_ID{td}has_column{td}DM_DEPOSIT_TXN có cột CUSTOMER_ID liên kết khách hàng
relation{td}DM_DEPOSIT_TXN{td}DM_DEPOSIT_TXN.TXN_DATE{td}has_column{td}DM_DEPOSIT_TXN có cột TXN_DATE
relation{td}DM_DEPOSIT_TXN{td}DM_DEPOSIT_TXN.BRANCH_ID{td}has_column{td}DM_DEPOSIT_TXN có cột BRANCH_ID
relation{td}DM_DEPOSIT_TXN{td}DM_CUSTOMER{td}joins_with{td}DM_DEPOSIT_TXN join với DM_CUSTOMER qua cột CUSTOMER_ID
relation{td}DM_DEPOSIT_TXN{td}RETAIL_BANKING{td}part_of{td}Bảng DM_DEPOSIT_TXN thuộc domain retail_banking
relation{td}DM_DEPOSIT_TXN{td}GIAO DỊCH TIỀN GỬI{td}refers_to{td}Bảng DM_DEPOSIT_TXN đại diện cho khái niệm nghiệp vụ giao dịch tiền gửi
relation{td}DM_DEPOSIT_TXN.CUSTOMER_ID{td}DM_CUSTOMER{td}refers_to{td}Cột CUSTOMER_ID tham chiếu đến bảng DM_CUSTOMER
{cd}
""".format(td=TUPLE_DELIMITER, cd=COMPLETION_DELIMITER)


ENTITY_EXTRACTION_SYSTEM = """\
---Role---
You are a Knowledge Graph Specialist for a Vietnamese banking data platform (FinX).
Your job is to extract a COMPREHENSIVE knowledge graph from the input text — covering
tables, columns, datasets, domains, business terms, source systems, and all relationships.

---Instructions---
1.  **Entity Extraction:**
    - For each entity, output 4 fields delimited by ``{td}``, on a single line.
    - First field must be the literal string ``entity``.
    - Format: ``entity{td}entity_name{td}entity_type{td}entity_description``

2.  **Relationship Extraction:**
    - For each relationship, output 5 fields delimited by ``{td}``, on a single line.
    - First field must be the literal string ``relation``.
    - Format: ``relation{td}source_entity{td}target_entity{td}relationship_keywords{td}relationship_description``

3.  **Delimiter rules:**
    - ``{td}`` is the field separator. Do NOT embed it inside any field.
    - Output ``{cd}`` on a final line when done.

4.  **Entity types:** {entity_types}
5.  **Edge types:** {edge_types}

6.  **What to extract — be COMPREHENSIVE:**

    a) **Table** — every table mentioned. Include database, dataset, domain in description.
    b) **Column** — extract ALL columns listed. Name format: ``TABLE_NAME.COLUMN_NAME``.
       Include data type, PK/partition flags, and business meaning in description.
    c) **Dataset** — datasets or data groups mentioned.
    d) **BusinessTerm** — Vietnamese or English business concepts implied by the table
       and its columns (e.g. "giao dịch tiền gửi", "chi nhánh", "khách hàng").
    e) **Concept** — domains, data sensitivity tags (PII), certification status,
       storage concepts, aggregation grains.
    f) **SourceAuthority** — source systems, databases, or data origins.
    g) **Metric / Dimension** — if metrics or dimensions are mentioned.

7.  **Relationships to extract — be THOROUGH:**
    - ``HAS_COLUMN``: Table → each Column (TABLE_NAME → TABLE_NAME.COL_NAME)
    - ``BELONGS_TO``: Table → Dataset
    - ``PART_OF``: Table → Domain concept
    - ``JOINS_WITH``: Table → other Tables mentioned in joins or foreign keys
    - ``REFERS_TO``: Column → referenced Table/Column (foreign keys)
    - ``REFERS_TO``: Table → BusinessTerm it represents
    - ``ALIAS_OF``: between synonymous BusinessTerms
    - ``BACKED_BY``: Table → SourceAuthority
    - ``DEFINED_AS``: for grain/aggregation definitions

8.  **Banking domain rules:**
    - Preserve EXACT Vietnamese terminology alongside English.
    - Banking abbreviations (TKTT, VND, KYC, AML, CIF, PII) must be kept as-is.
    - Extract business terms from Vietnamese descriptions (e.g. "chi nhánh" → BusinessTerm).
    - If a column references another table (foreign key, join key), create a REFERS_TO edge.
    - Prefer RECALL over precision — extract everything meaningful, do NOT skip content.

9.  **Output language:** Vietnamese descriptions preferred when source is Vietnamese,
    with English translation in parentheses when helpful.

---Examples---
{examples}
""".format(
    td=TUPLE_DELIMITER,
    cd=COMPLETION_DELIMITER,
    entity_types=", ".join(ENTITY_TYPES),
    edge_types=", ".join(EDGE_TYPES),
    examples=_EXTRACTION_EXAMPLES,
)

# ── User prompt: extraction ───────────────────────────────────────────────────

ENTITY_EXTRACTION_USER = """\
---Task---
Extract a COMPREHENSIVE knowledge graph from the text below.
Extract ALL entities (tables, columns, datasets, business terms, concepts) and ALL relationships.
Do NOT skip columns or implicit relationships. Be thorough.

---Instructions---
1. Follow ALL format rules from the system prompt strictly.
2. Output ONLY entity and relation lines — no commentary, no explanations.
3. Extract EVERY column as a Column entity with name format TABLE_NAME.COLUMN_NAME.
4. Extract business terms from Vietnamese descriptions.
5. Extract join/FK relationships between tables when columns reference other tables.
6. Output ``{cd}`` on the final line.

---Data---
<Input Text>
```
{{input_text}}
```

<Output>
""".format(cd=COMPLETION_DELIMITER)

# ── Gleaning prompt: ask LLM to find missed entities ──────────────────────────

ENTITY_CONTINUE_EXTRACTION = """\
---Task---
Based on the last extraction, identify any MISSED entities or relationships.
Focus on:
- Columns that were not extracted
- Business terms from Vietnamese descriptions
- Join/FK relationships implied by column names (e.g. customer_id → customer table)
- Domain/data sensitivity concepts (PII, data quality, certification)

---Instructions---
1. Do NOT re-output already-extracted items.
2. Only output NEW or CORRECTED items.
3. Use the exact same format (entity/relation lines).
4. Output ``{cd}`` when done.

<Output>
""".format(cd=COMPLETION_DELIMITER)

# ── Description summary prompt ────────────────────────────────────────────────

DESCRIPTION_SUMMARY = """\
---Role---
You are a Knowledge Graph Specialist. Synthesize these descriptions of "{entity_name}"
into ONE concise, comprehensive summary.

---Instructions---
1. Integrate all key facts from every description.
2. Output plain text (no JSON, no markdown).
3. Preserve Vietnamese terminology.
4. Maximum 200 words.

---Descriptions---
{descriptions}

---Output---
"""
