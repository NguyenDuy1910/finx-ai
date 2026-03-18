
from __future__ import annotations

import asyncio
import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from common import log


# ── File reader ───────────────────────────────────────────────────────────────

def read_json_dir(directory: str | Path) -> list[dict]:
    """Load all .json files from a local directory."""
    items = []
    d = Path(directory)
    if not d.exists():
        log.warning("Directory does not exist: %s", d)
        return items
    for f in sorted(d.glob("*.json")):
        try:
            data = json.loads(f.read_text())
            if isinstance(data, dict):
                data.setdefault("name", f.stem)
                items.append(data)
            elif isinstance(data, list):
                for i, item in enumerate(data):
                    if isinstance(item, dict):
                        item.setdefault("name", f"{f.stem}_{i}")
                        items.append(item)
        except Exception as exc:
            log.warning("Could not load %s: %s", f, exc)
    log.info("read_json_dir: loaded %d items from %s", len(items), d)
    return items


def read_text_files(directory: str | Path, ext: str = "*.md") -> list[dict]:
    """Load all text/markdown files from a directory."""
    items = []
    d = Path(directory)
    if not d.exists():
        return items
    for f in sorted(d.glob(ext)):
        content = f.read_text(errors="replace").strip()
        if content:
            items.append({"name": f.stem, "content": content, "source_file": str(f)})
    log.info("read_text_files: loaded %d items from %s", len(items), d)
    return items


# ── Athena query-result reader (local files) ──────────────────────────────────

def athena_query_to_text(directory: str | Path) -> list[dict]:
    """Read Athena query result files (CSV/TSV) from a local directory and
    convert each into a text item suitable for 9Router processing.

    Supports .csv and .tsv files.  Each file becomes one item with a readable
    text representation of its rows.
    """
    import csv

    items: list[dict] = []
    d = Path(directory)
    if not d.exists():
        return items

    for f in sorted(d.glob("*.csv")) + sorted(d.glob("*.tsv")):
        try:
            delimiter = "\t" if f.suffix == ".tsv" else ","
            with f.open(newline="", errors="replace") as fh:
                reader = csv.DictReader(fh, delimiter=delimiter)
                rows = list(reader)

            if not rows:
                continue

            # build human-readable text
            headers = list(rows[0].keys())
            lines = [f"Source: {f.name}", f"Columns: {', '.join(headers)}", ""]
            for row in rows:
                line_parts = [f"{h}: {row.get(h, '')}" for h in headers]
                lines.append(" | ".join(line_parts))

            items.append({
                "name": f.stem,
                "source_file": str(f),
                "row_count": len(rows),
                "content": "\n".join(lines),
            })
        except Exception as exc:
            log.warning("Could not read %s: %s", f, exc)

    log.info("athena_query_to_text: loaded %d files from %s", len(items), d)
    return items


# ── Athena live reader ────────────────────────────────────────────────────────

# Default concurrency: how many DESCRIBE EXTENDED queries run in parallel.
ATHENA_CONCURRENCY = int(os.getenv("ATHENA_CONCURRENCY", "20"))


def _submit_query(client, sql: str, database: str, workgroup: str, output_loc: str) -> str:
    """Fire-and-forget: submit a query and return the QueryExecutionId immediately."""
    resp = client.start_query_execution(
        QueryString=sql,
        QueryExecutionContext={"Database": database},
        WorkGroup=workgroup,
        ResultConfiguration={"OutputLocation": output_loc},
    )
    return resp["QueryExecutionId"]


def _wait_for_query(client, qid: str) -> tuple[str, str]:
    """Poll until the query finishes. Returns (qid, state)."""
    for attempt in range(90):
        status = client.get_query_execution(QueryExecutionId=qid)
        state = status["QueryExecution"]["Status"]["State"]
        if state in ("SUCCEEDED", "FAILED", "CANCELLED"):
            return qid, state
        if attempt % 5 == 0 and attempt > 0:
            log.debug("  Waiting for %s ... (%ds elapsed)", qid, attempt * 2)
        time.sleep(2)
    return qid, "TIMEOUT"


def _fetch_rows(client, qid: str) -> list[list[str]]:
    """Fetch all result rows (skipping header) for a completed query."""
    paginator = client.get_paginator("get_query_results")
    rows: list[list[str]] = []
    first_page = True
    for page in paginator.paginate(QueryExecutionId=qid):
        for row in page["ResultSet"]["Rows"]:
            if first_page:
                first_page = False
                continue  # skip header
            rows.append([col.get("VarCharValue", "") for col in row["Data"]])
    return rows


# ---------------------------------------------------------------------------
# Glue API — rich table metadata (no Athena query charge)
# ---------------------------------------------------------------------------

def _glue_get_table(glue_client, database: str, tname: str) -> dict | None:
    """Fetch full table metadata from Glue Data Catalog. Returns None on error."""
    try:
        resp = glue_client.get_table(DatabaseName=database, Name=tname)
        return resp.get("Table", {})
    except Exception as exc:
        log.debug("  Glue get_table failed for %s.%s — %s", database, tname, exc)
        return None


def _parse_glue_table(database: str, tname: str, glue_table: dict) -> dict:
    """
    Convert a Glue Table object into the rich schema dict used by the LLM prompt.

    Extracts:
      - All regular columns (name, type, comment)
      - Partition columns (name, type, comment) — marked is_partition_key=True
      - Storage format (InputFormat → PARQUET / ORC / CSV / …)
      - S3 location
      - Table-level comment / description
      - Table parameters (row count, classification, etc.)
      - Owner
    """
    sd = glue_table.get("StorageDescriptor", {})

    # ── columns ──────────────────────────────────────────────────────────────
    def _map_col(c: dict, is_partition: bool = False) -> dict:
        return {
            "name":             c.get("Name", ""),
            "data_type":        c.get("Type", ""),
            "description":      c.get("Comment", ""),
            "is_partition_key": is_partition,
        }

    regular_cols   = [_map_col(c) for c in sd.get("Columns", [])]
    partition_cols = [_map_col(c, is_partition=True)
                      for c in glue_table.get("PartitionKeys", [])]
    all_columns    = regular_cols + partition_cols

    # ── storage format ────────────────────────────────────────────────────────
    input_fmt = sd.get("InputFormat", "")
    fmt_map = {
        "parquet":  "PARQUET",
        "orc":      "ORC",
        "avro":     "AVRO",
        "json":     "JSON",
        "csv":      "CSV",
        "textfile": "CSV",
        "delta":    "DELTA",
    }
    storage_format = next(
        (v for k, v in fmt_map.items() if k in input_fmt.lower()),
        input_fmt.split(".")[-1].upper() if input_fmt else "",
    )

    # ── table parameters ──────────────────────────────────────────────────────
    params       = glue_table.get("Parameters", {})
    row_count    = None
    try:
        raw_rc = params.get("numRows") or params.get("num_rows") or params.get("rowCount")
        if raw_rc:
            row_count = int(raw_rc)
    except (ValueError, TypeError):
        pass

    classification = params.get("classification", "")
    table_comment  = (
        glue_table.get("Description", "")
        or params.get("comment", "")
        or params.get("spark.sql.sources.schema.description", "")
    )
    s3_location    = sd.get("Location", "")
    owner          = glue_table.get("Owner", "")
    table_type     = glue_table.get("TableType", "")   # EXTERNAL_TABLE / VIRTUAL_VIEW / …

    # ── human-readable content for the LLM ───────────────────────────────────
    lines: list[str] = [
        f"database: {database}",
        f"table: {tname}",
        f"table_type: {table_type}" if table_type else "",
        f"description: {table_comment}" if table_comment else "",
        f"storage_format: {storage_format}" if storage_format else "",
        f"location: {s3_location}" if s3_location else "",
        f"owner: {owner}" if owner else "",
        f"row_count: {row_count}" if row_count is not None else "",
        f"classification: {classification}" if classification else "",
        "",
        "columns:",
    ]
    for col in regular_cols:
        comment_part = f"  -- {col['description']}" if col["description"] else ""
        lines.append(f"  {col['name']}  {col['data_type']}{comment_part}")

    if partition_cols:
        lines.append("")
        lines.append("partition_columns:")
        for col in partition_cols:
            comment_part = f"  -- {col['description']}" if col["description"] else ""
            lines.append(f"  {col['name']}  {col['data_type']}{comment_part}")

    # extra parameters the LLM can use
    extra_params = {k: v for k, v in params.items()
                    if k not in ("numRows", "num_rows", "rowCount", "comment",
                                 "classification", "EXTERNAL", "transient_lastDdlTime")}
    if extra_params:
        lines.append("")
        lines.append("table_properties:")
        for k, v in list(extra_params.items())[:10]:   # cap to avoid noise
            lines.append(f"  {k}: {v}")

    return {
        "name":             tname,
        "database":         database,
        "table_comment":    table_comment,
        "storage_format":   storage_format,
        "s3_location":      s3_location,
        "owner":            owner,
        "table_type":       table_type,
        "row_count":        row_count,
        "columns":          all_columns,
        "partition_keys":   [c["name"] for c in partition_cols],
        "content":          "\n".join(line for line in lines if line is not None),
    }


# ---------------------------------------------------------------------------
# Fallback: DESCRIBE EXTENDED via Athena (when Glue is unavailable)
# ---------------------------------------------------------------------------

def _parse_describe_extended(database: str, tname: str, rows: list[list[str]]) -> dict:
    """
    Parse the output of `DESCRIBE EXTENDED <table>` into a rich schema dict.

    DESCRIBE EXTENDED returns three sections separated by blank rows:
      1. Column definitions  (col_name | data_type | comment)
      2. Partition info      (col_name | data_type | comment)
      3. Detailed table info (property | value | "")

    Everything is extracted and assembled into a LLM-friendly text block.
    """
    regular_cols:   list[dict] = []
    partition_cols: list[dict] = []
    table_props:    dict[str, str] = {}

    # State machine: "columns" → "partitions" → "detailed_info"
    section = "columns"

    for row in rows:
        col_name = row[0].strip() if len(row) > 0 else ""
        col_type = row[1].strip() if len(row) > 1 else ""
        comment  = row[2].strip() if len(row) > 2 else ""

        # Section separators are empty col_name rows or rows like "# col_name  data_type  comment"
        if not col_name or col_name.startswith("#"):
            if "Partition Information" in col_name or "Partition Information" in col_type:
                section = "partitions"
            elif "Detailed Table Information" in col_name or "Table Parameters" in col_type:
                section = "detailed_info"
            continue

        if section == "columns":
            regular_cols.append({
                "name": col_name, "data_type": col_type,
                "description": comment, "is_partition_key": False,
            })
        elif section == "partitions":
            partition_cols.append({
                "name": col_name, "data_type": col_type,
                "description": comment, "is_partition_key": True,
            })
        elif section == "detailed_info":
            # col_name = property key, col_type = property value
            table_props[col_name.rstrip(":")] = col_type

    # Extract useful fields from table_props
    storage_format = ""
    raw_fmt = table_props.get("InputFormat", table_props.get("Storage Desc Parameters", ""))
    for k, v in {"parquet": "PARQUET", "orc": "ORC", "avro": "AVRO",
                 "json": "JSON", "csv": "CSV", "delta": "DELTA"}.items():
        if k in raw_fmt.lower():
            storage_format = v
            break

    row_count = None
    try:
        raw_rc = table_props.get("numRows") or table_props.get("Statistics")
        if raw_rc:
            m = re.search(r"\d+", raw_rc)
            if m:
                row_count = int(m.group())
    except (ValueError, TypeError):
        pass

    table_comment = table_props.get("Comment", table_props.get("comment", ""))
    s3_location   = table_props.get("Location", "")
    owner         = table_props.get("Owner", "")

    all_columns = regular_cols + partition_cols

    # Build human-readable content
    lines: list[str] = [
        f"database: {database}",
        f"table: {tname}",
        f"description: {table_comment}" if table_comment else "",
        f"storage_format: {storage_format}" if storage_format else "",
        f"location: {s3_location}" if s3_location else "",
        f"owner: {owner}" if owner else "",
        f"row_count: {row_count}" if row_count is not None else "",
        "",
        "columns:",
    ]
    for col in regular_cols:
        suffix = f"  -- {col['description']}" if col["description"] else ""
        lines.append(f"  {col['name']}  {col['data_type']}{suffix}")

    if partition_cols:
        lines.append("")
        lines.append("partition_columns:")
        for col in partition_cols:
            suffix = f"  -- {col['description']}" if col["description"] else ""
            lines.append(f"  {col['name']}  {col['data_type']}{suffix}")

    return {
        "name":           tname,
        "database":       database,
        "table_comment":  table_comment,
        "storage_format": storage_format,
        "s3_location":    s3_location,
        "owner":          owner,
        "row_count":      row_count,
        "columns":        all_columns,
        "partition_keys": [c["name"] for c in partition_cols],
        "content":        "\n".join(line for line in lines if line is not None),
    }


def _fetch_table_columns(
    client,
    glue_client,
    database: str,
    tname: str,
    workgroup: str,
    output_loc: str,
) -> tuple[str, dict | None, str]:
    """
    Fetch FULL table schema for one table using:
      1. Glue Data Catalog API  (preferred — free, fast, richest metadata)
      2. DESCRIBE EXTENDED      (fallback — handles views + non-Glue tables)
      3. SHOW COLUMNS           (last resort — minimal type info only)

    Returns (tname, schema_dict_or_None, error_message).
    """
    # ── Strategy 1: Glue API ─────────────────────────────────────────────────
    if glue_client is not None:
        glue_table = _glue_get_table(glue_client, database, tname)
        if glue_table:
            return tname, _parse_glue_table(database, tname, glue_table), ""

    # ── Strategy 2: DESCRIBE EXTENDED ────────────────────────────────────────
    try:
        qid = _submit_query(
            client,
            sql=f"DESCRIBE EXTENDED `{database}`.`{tname}`",
            database=database,
            workgroup=workgroup,
            output_loc=output_loc,
        )
        qid, state = _wait_for_query(client, qid)
        if state == "SUCCEEDED":
            rows = _fetch_rows(client, qid)
            return tname, _parse_describe_extended(database, tname, rows), ""
        # DESCRIBE EXTENDED failed → fall through to SHOW COLUMNS
        log.debug("  DESCRIBE EXTENDED failed for %s (%s), trying SHOW COLUMNS", tname, state)
    except Exception as exc:
        log.debug("  DESCRIBE EXTENDED exception for %s — %s", tname, exc)

    # ── Strategy 3: SHOW COLUMNS (minimal fallback) ──────────────────────────
    try:
        qid = _submit_query(
            client,
            sql=f"SHOW COLUMNS IN `{database}`.`{tname}`",
            database=database,
            workgroup=workgroup,
            output_loc=output_loc,
        )
        qid, state = _wait_for_query(client, qid)
        if state != "SUCCEEDED":
            status = client.get_query_execution(QueryExecutionId=qid)
            reason = status["QueryExecution"]["Status"].get("StateChangeReason", state)
            return tname, None, reason

        col_rows = _fetch_rows(client, qid)
        columns = []
        for row in col_rows:
            if len(row) >= 2:
                columns.append({"name": row[0].strip(), "data_type": row[1].strip(),
                                 "description": "", "is_partition_key": False})
            elif row and row[0].strip():
                parts = row[0].split("\t", 1)
                columns.append({"name": parts[0].strip(),
                                 "data_type": parts[1].strip() if len(parts) > 1 else "",
                                 "description": "", "is_partition_key": False})

        # Try to enrich with partition info via SHOW PARTITIONS (best-effort)
        partition_key_names: list[str] = []
        try:
            pqid = _submit_query(
                client,
                sql=f"SHOW PARTITIONS `{database}`.`{tname}`",
                database=database,
                workgroup=workgroup,
                output_loc=output_loc,
            )
            pqid, pstate = _wait_for_query(client, pqid)
            if pstate == "SUCCEEDED":
                prows = _fetch_rows(client, pqid)
                # Each row looks like: ["dt=2024-01-01/bank_code=VCB"]
                # Extract unique partition key names from the first row
                if prows:
                    sample = prows[0][0] if prows[0] else ""
                    for part in sample.split("/"):
                        if "=" in part:
                            partition_key_names.append(part.split("=", 1)[0].strip())
        except Exception:
            pass  # SHOW PARTITIONS may fail on unpartitioned tables — silently skip

        # Mark matching columns as partition keys
        for col in columns:
            if col["name"] in partition_key_names:
                col["is_partition_key"] = True

        lines = [f"database: {database}", f"table: {tname}", ""]
        if partition_key_names:
            lines.append(f"partition_keys: {', '.join(partition_key_names)}")
            lines.append("")
        lines += ["columns:"] + [
            f"  {c['name']}  {c['data_type']}"
            + (" [PARTITION]" if c["is_partition_key"] else "")
            for c in columns
        ]
        return tname, {
            "name": tname, "database": database,
            "columns": columns, "partition_keys": partition_key_names,
            "content": "\n".join(lines),
        }, ""

    except Exception as exc:
        return tname, None, str(exc)


def read_athena_schemas(
    database: str | None = None,
    concurrency: int | None = None,
) -> list[dict]:
    """Query Athena/Glue to get FULL table schema metadata for a database.

    Metadata fetched per table
    --------------------------
    - All column names, types, and comments (from Glue or DESCRIBE EXTENDED)
    - Partition columns (marked is_partition_key=True)
    - Storage format (PARQUET / ORC / AVRO / …)
    - S3 location
    - Table-level description / comment
    - Row count (from Glue statistics)
    - Owner, table type (EXTERNAL_TABLE / VIRTUAL_VIEW)
    - Extra table parameters (classification, etc.)

    Strategy per table
    ------------------
    1. Glue Data Catalog API  — preferred, free, richest detail, no Athena charge
    2. DESCRIBE EXTENDED       — fallback for views / non-Glue tables
    3. SHOW COLUMNS            — last resort (type info only)

    Environment
    -----------
    ATHENA_CONCURRENCY   parallel workers (default: 20)
    """
    import boto3

    database    = database    or os.getenv("ATHENA_DATABASE")
    workgroup   = os.getenv("ATHENA_WORKGROUP", "primary")
    output_loc  = os.environ["ATHENA_OUTPUT_LOCATION"]
    region      = os.getenv("AWS_REGION", "ap-southeast-1")
    concurrency = concurrency or ATHENA_CONCURRENCY

    log.info("━━━ Athena/Glue  database=%-32s workgroup=%s  concurrency=%d",
             database, workgroup, concurrency)

    athena_client = boto3.client("athena", region_name=region)

    # Try to build a Glue client — if credentials don't have glue:GetTable it
    # will fail gracefully per-table and fall back to DESCRIBE EXTENDED.
    try:
        glue_client = boto3.client("glue", region_name=region)
        # quick smoke-test: list databases (very cheap)
        glue_client.get_database(Name=database)
        log.info("  Glue API available — using rich Glue metadata")
    except Exception:
        glue_client = None
        log.info("  Glue API unavailable — falling back to DESCRIBE EXTENDED")

    # ── Step 1: list tables ───────────────────────────────────────────────────
    log.info("  [1/2] Listing tables in %s ...", database)
    t0 = time.time()
    try:
        qid = _submit_query(athena_client, f"SHOW TABLES IN `{database}`",
                            database, workgroup, output_loc)
        qid, state = _wait_for_query(athena_client, qid)
        if state != "SUCCEEDED":
            raise RuntimeError(f"SHOW TABLES {state}")
        table_names = [r[0].strip() for r in _fetch_rows(athena_client, qid) if r and r[0].strip()]
    except Exception as exc:
        log.error("  FAILED to list tables in %s — %s", database, exc)
        return []

    total = len(table_names)
    log.info("  [1/2] Found %d tables (%.1fs)", total, time.time() - t0)

    # ── Step 2: parallel schema fetch ─────────────────────────────────────────
    log.info("  [2/2] Fetching full schema (%d tables, %d parallel) ...", total, concurrency)
    t1 = time.time()

    tables:    dict[str, dict] = {}
    skipped:   list[str]       = []
    done_count = 0

    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        future_to_table = {
            pool.submit(
                _fetch_table_columns,
                athena_client, glue_client, database, tname, workgroup, output_loc
            ): tname
            for tname in table_names
        }

        for future in as_completed(future_to_table):
            tname, schema, error = future.result()
            done_count += 1
            pct = done_count * 100 // total

            if schema is None:
                skipped.append(tname)
                log.warning("  [%3d/%d | %3d%%] ⚠  %-45s  SKIPPED — %s",
                            done_count, total, pct, tname, error)
            else:
                n_cols   = len(schema.get("columns", []))
                n_parts  = len(schema.get("partition_keys", []))
                has_desc = "✎" if schema.get("table_comment") else " "
                fmt      = schema.get("storage_format", "")
                log.info("  [%3d/%d | %3d%%] ✓ %s %-42s  %2d cols  %d part  %s  %s",
                         done_count, total, pct, has_desc, tname,
                         n_cols, n_parts, fmt, schema.get("owner", ""))
                tables[tname] = schema

    elapsed = time.time() - t1
    log.info("━━━ Done  loaded=%d  skipped=%d  elapsed=%.1fs  database=%s",
             len(tables), len(skipped), elapsed, database)
    if skipped:
        log.warning("  Skipped tables (%d): %s", len(skipped), ", ".join(skipped))

    return list(tables.values())



# ── Confluence reader ─────────────────────────────────────────────────────────

def _extract_page_id_from_url(url: str) -> str | None:
    """Extract numeric page ID from a Confluence page URL.

    Handles both formats:
      https://org.atlassian.net/wiki/spaces/SPACE/pages/123456789/Page+Title
      https://org.atlassian.net/wiki/spaces/SPACE/pages/123456789
    """
    m = re.search(r"/pages/(\d+)", url)
    return m.group(1) if m else None


def read_confluence_page(page_url: str | None = None) -> dict | None:
    """Fetch a single Confluence page by URL.

    The page URL is read from the `page_url` argument or the
    ``CONFLUENCE_PAGE_URL`` env var.

    Required env vars:
      CONFLUENCE_URL        — e.g. https://your-org.atlassian.net
      CONFLUENCE_USERNAME   — Atlassian account email
      CONFLUENCE_API_TOKEN  — API token from id.atlassian.com

    Optional env vars:
      CONFLUENCE_PAGE_URL   — full URL of the page to fetch
    """
    from atlassian import Confluence

    base_url  = os.environ["CONFLUENCE_URL"]
    username  = os.environ["CONFLUENCE_USERNAME"]
    api_token = os.environ["CONFLUENCE_API_TOKEN"]
    page_url  = page_url or os.environ.get("CONFLUENCE_PAGE_URL", "")

    if not page_url:
        raise ValueError(
            "No Confluence page URL provided. "
            "Set CONFLUENCE_PAGE_URL env var or pass --url on the command line."
        )

    page_id = _extract_page_id_from_url(page_url)
    if not page_id:
        raise ValueError(
            f"Could not extract a numeric page ID from URL: {page_url}\n"
            "Expected format: https://your-org.atlassian.net/wiki/spaces/SPACE/pages/<ID>/..."
        )

    client = Confluence(url=base_url, username=username, password=api_token, cloud=True)

    try:
        page = client.get_page_by_id(page_id, expand="body.storage,space")
    except Exception as exc:
        log.error("Confluence API error fetching page %s — %s", page_id, exc)
        return None

    if not page:
        log.warning("Page %s not found in Confluence", page_id)
        return None

    import html as html_mod

    title     = page.get("title", "")
    space_key = page.get("space", {}).get("key", "")
    body_html = page.get("body", {}).get("storage", {}).get("value", "")
    clean     = re.sub(r"<[^>]+>", " ", body_html)
    clean     = html_mod.unescape(re.sub(r"\s+", " ", clean).strip())

    if not clean:
        log.warning("Page '%s' has no extractable text content", title)
        return None

    canonical_url = f"{base_url.rstrip('/')}/wiki/spaces/{space_key}/pages/{page_id}"
    log.info("read_confluence_page: '%s'  id=%s  url=%s", title, page_id, canonical_url)
    return {
        "name":    f"{space_key}_{page_id}",
        "title":   title,
        "space":   space_key,
        "page_id": page_id,
        "url":     canonical_url,
        "content": f"# {title}\n\n{clean}",
        "raw_html": body_html,
    }


def read_confluence_page_list(
    space_keys: list[str],
    base_url: str,
    username: str,
    api_token: str,
    limit: int = 2000,
) -> list[dict]:
    """List all pages in Confluence spaces — fetches metadata only (no body).

    Returns a list of lightweight dicts:
      {"page_id": "123", "title": "...", "space": "DATA", "url": "..."}

    Cheap — no body.storage expand, just id + title + space.
    """
    from atlassian import Confluence

    client = Confluence(url=base_url, username=username, password=api_token, cloud=True)
    pages: list[dict] = []

    for space in space_keys:
        start = 0
        log.info("  Listing pages in space %s ...", space)
        while True:
            batch = client.get_all_pages_from_space(
                space, start=start, limit=50, expand="version"
            )
            if not batch:
                break
            for p in batch:
                page_id = p.get("id", "")
                pages.append({
                    "page_id": page_id,
                    "title":   p.get("title", ""),
                    "space":   space,
                    "url":     f"{base_url.rstrip('/')}/wiki/spaces/{space}/pages/{page_id}",
                })
            start += len(batch)
            if len(batch) < 50 or len(pages) >= limit:
                break
        log.info("  Space %s — %d pages listed so far", space, len(pages))

    log.info("read_confluence_page_list: %d pages across %s", len(pages), space_keys)
    return pages


    """Fetch pages from Confluence spaces.

    Required env vars:
      CONFLUENCE_URL        — e.g. https://your-org.atlassian.net
      CONFLUENCE_USERNAME   — Atlassian account email
      CONFLUENCE_API_TOKEN  — API token from id.atlassian.com/manage-profile/security/api-tokens

    Optional env vars:
      CONFLUENCE_SPACE_KEYS — comma-separated space keys (default: DATA)
    """
    from atlassian import Confluence

    base_url  = os.environ["CONFLUENCE_URL"]
    username  = os.environ["CONFLUENCE_USERNAME"]
    api_token = os.environ["CONFLUENCE_API_TOKEN"]
    space_keys = space_keys or [
        s.strip() for s in os.getenv("CONFLUENCE_SPACE_KEYS", "DATA").split(",") if s.strip()
    ]

    client = Confluence(url=base_url, username=username, password=api_token, cloud=True)
    items = []

    for space in space_keys:
        start = 0
        while True:
            pages = client.get_all_pages_from_space(space, start=start, limit=50, expand="body.storage")
            if not pages:
                break
            for page in pages:
                title = page.get("title", "")
                body_html = page.get("body", {}).get("storage", {}).get("value", "")
                clean = re.sub(r"<[^>]+>", " ", body_html)
                clean = re.sub(r"\s+", " ", clean).strip()
                if clean:
                    page_id = page.get("id", "")
                    items.append({
                        "name":    f"{space}_{page_id}",
                        "title":   title,
                        "space":   space,
                        "page_id": page_id,
                        "url":     f"{base_url.rstrip('/')}/wiki/spaces/{space}/pages/{page_id}",
                        "content": f"# {title}\n\n{clean}",
                    })
            start += len(pages)
            if len(pages) < 50 or len(items) >= limit:
                break

    log.info("read_confluence_pages: loaded %d pages", len(items))
    return items
