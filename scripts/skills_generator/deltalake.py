"""
Generic Delta Lake store — schema-driven write and query.

Pure data layer: no API knowledge, no HTTP calls.
Operates on table schemas + Polars DataFrames only.
Reusable across any scenario that needs Delta Lake I/O.

Delta Lake REQUIRES S3 / object storage — local filesystem paths are rejected.
"""
from __future__ import annotations

from typing import Any

import duckdb
import polars as pl
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


# ── Shared config (imported by skill run.py) ────────────────────────

class StorageConfig(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")
    root: str = ""  # Must be an S3 URL, e.g. s3://my-bucket/delta
    tenant: str = "default"
    storage_options: dict[str, Any] | None = None

    @field_validator("root")
    @classmethod
    def must_be_s3(cls, v: str) -> str:
        if not v:
            raise ValueError(
                "storage.root must be set to an S3 URL (e.g. s3://my-bucket/delta). "
                "Delta Lake does not support local filesystem storage."
            )
        if not v.startswith("s3://"):
            raise ValueError(
                f"storage.root must start with 's3://', got: {v!r}. "
                "Delta Lake requires S3 / object storage — local paths are not supported."
            )
        return v


# ── Type map (shared short-name → Polars/DuckDB) ────────────────────

TYPE_MAP: dict[str, dict[str, str]] = {
    "i8":          {"polars": "Int8",          "duckdb": "TINYINT"},
    "i16":         {"polars": "Int16",         "duckdb": "SMALLINT"},
    "i32":         {"polars": "Int32",         "duckdb": "INTEGER"},
    "i64":         {"polars": "Int64",         "duckdb": "BIGINT"},
    "u8":          {"polars": "UInt8",         "duckdb": "UTINYINT"},
    "u16":         {"polars": "UInt16",        "duckdb": "USMALLINT"},
    "u32":         {"polars": "UInt32",        "duckdb": "UINTEGER"},
    "u64":         {"polars": "UInt64",        "duckdb": "UBIGINT"},
    "f32":         {"polars": "Float32",       "duckdb": "FLOAT"},
    "f64":         {"polars": "Float64",       "duckdb": "DOUBLE"},
    "str":         {"polars": "String",        "duckdb": "VARCHAR"},
    "bool":        {"polars": "Boolean",       "duckdb": "BOOLEAN"},
    "date":        {"polars": "Date",          "duckdb": "DATE"},
    "time":        {"polars": "Time",          "duckdb": "TIME"},
    "datetime":    {"polars": "Datetime('us')","duckdb": "TIMESTAMP"},
    "timestamptz": {"polars": "Datetime('us','UTC')", "duckdb": "TIMESTAMP WITH TIME ZONE"},
    "duration":    {"polars": "Duration('us')","duckdb": "INTERVAL"},
    "binary":      {"polars": "Binary",        "duckdb": "BLOB"},
    "json":        {"polars": "String",        "duckdb": "JSON"},
}


def polars_dtype(type_str: str) -> pl.DataType:
    """Convert a short type name to a Polars dtype."""
    return getattr(pl, TYPE_MAP[type_str]["polars"])


def duckdb_type(type_str: str) -> str:
    """Convert a short type name to a DuckDB SQL type."""
    return TYPE_MAP[type_str]["duckdb"]


# ── Path resolution ─────────────────────────────────────────────────

def delta_path(table_cfg: dict, storage_root: str, tenant: str) -> str:
    """Resolve the filesystem/S3 path for a table."""
    return f"{storage_root}/{tenant}/{table_cfg['name']}"


# ── Table lifecycle ─────────────────────────────────────────────────

def table_exists(path: str, storage_options: dict[str, Any] | None = None) -> bool:
    """Check if a Delta table exists at the given S3 path."""
    from deltalake import DeltaTable
    from deltalake.exceptions import TableNotFoundError
    try:
        so = storage_options or {}
        DeltaTable(path, storage_options=so)
        return True
    except (TableNotFoundError, Exception):
        return False


def open_or_create_table(
    table_cfg: dict, path: str, storage_options: dict[str, Any] | None = None,
) -> Any:
    """Open existing Delta table or create one from schema."""
    from deltalake import DeltaTable, write_deltalake

    so = storage_options or {}
    if not table_exists(path, so):
        schema_fields = []
        for f in table_cfg["fields"]:
            if f.get("generated"):
                continue
            dtype = polars_dtype(f["type"])
            series = pl.Series(f["name"], [], dtype=dtype)
            schema_fields.append(series)
        empty_df = pl.DataFrame({s.name: s for s in schema_fields})
        write_deltalake(path, empty_df, mode="overwrite", storage_options=so)

    return DeltaTable(path, storage_options=so)


# ── DuckDB S3 configuration ─────────────────────────────────────────

def _configure_duckdb_s3(con: duckdb.DuckDBPyConnection, storage_options: dict[str, Any]) -> None:
    """Configure DuckDB to access Delta tables on S3 via httpfs + delta extensions."""
    con.execute("INSTALL httpfs; LOAD httpfs;")
    con.execute("INSTALL delta; LOAD delta;")
    if storage_options.get("aws_access_key_id"):
        con.execute(f"SET s3_access_key_id = '{storage_options['aws_access_key_id']}'")
    if storage_options.get("aws_secret_access_key"):
        con.execute(f"SET s3_secret_access_key = '{storage_options['aws_secret_access_key']}'")
    if storage_options.get("aws_region"):
        con.execute(f"SET s3_region = '{storage_options['aws_region']}'")
    if storage_options.get("endpoint"):
        con.execute(f"SET s3_endpoint = '{storage_options['endpoint']}'")
    if storage_options.get("aws_session_token"):
        con.execute(f"SET s3_session_token = '{storage_options['aws_session_token']}'")


def last_update(
    table: Any, update_field: str, storage_options: dict[str, Any] | None = None,
) -> str | None:
    """Get max(update_field) from an existing Delta table via DuckDB + delta_scan."""
    so = storage_options or {}
    con = duckdb.connect()
    _configure_duckdb_s3(con, so)
    try:
        rows = con.execute(
            f"SELECT max(\"{update_field}\") FROM delta_scan('{table.table_uri}')"
        ).fetchone()
        return rows[0] if rows and rows[0] else None
    finally:
        con.close()


# ── Write ───────────────────────────────────────────────────────────

def write_records(
    table_cfg: dict,
    records: list[dict],
    storage_root: str,
    tenant: str = "default",
    generated_values: dict[str, str] | None = None,
    storage_options: dict[str, Any] | None = None,
) -> int:
    """
    Write raw records to a Delta table based on schema.

    Args:
        table_cfg:      Table definition (name, fields with types + originals).
        records:        List of dicts with API-field keys (matching `original` or `name`).
        storage_root:   Root path for all delta tables (S3 URL).
        tenant:         Tenant subdirectory.
        generated_values:  Dict of generated field name → value (e.g. {"org_path": "/a/b"}).
        storage_options:  S3 credentials passed to deltalake.

    Returns:
        Number of records written.
    """
    from deltalake import write_deltalake

    if not records:
        return 0

    so = storage_options or {}
    path = delta_path(table_cfg, storage_root, tenant)

    # Build rename map (original → name)
    rename_map = {}
    for f in table_cfg["fields"]:
        if f.get("original") and f["original"] != f["name"]:
            rename_map[f["original"]] = f["name"]

    # Collect expected API keys
    api_keys = [f.get("original", f["name"]) for f in table_cfg["fields"] if not f.get("generated")]

    # Filter and keep only declared keys
    filtered = [{k: r.get(k) for k in api_keys if k in r} for r in records]

    df = pl.DataFrame(filtered)

    # Rename columns to canonical names
    if rename_map:
        df = df.rename(rename_map)

    # Cast to declared types
    for f in table_cfg["fields"]:
        if not f.get("generated") and f["type"] in TYPE_MAP:
            try:
                df = df.with_columns(pl.col(f["name"]).cast(polars_dtype(f["type"])))
            except Exception:
                pass

    # Inject generated fields
    if generated_values:
        for f in table_cfg["fields"]:
            if f.get("generated") and f["name"] in generated_values:
                df = df.with_columns(pl.lit(generated_values[f["name"]]).alias(f["name"]))

    write_deltalake(path, df, mode="append", storage_options=so)
    return len(df)


# ── Query ───────────────────────────────────────────────────────────

# Statement types allowed for read-only Delta Lake queries
_ALLOWED_STMT_TYPES = frozenset({
    "SELECT",   # normal queries, CTEs, subqueries
    "PRAGMA",   # introspection commands
    "ANALYZE",  # statistics collection
    "EXPLAIN",  # query plan inspection
})


def validate_sql(sql: str) -> None:
    """Validate SQL using DuckDB's parser — reject any non-SELECT statement."""
    statements = duckdb.extract_statements(sql)
    if not statements:
        raise ValueError("Empty or unparseable SQL")
    for stmt in statements:
        type_name = stmt.type.name if hasattr(stmt.type, "name") else str(stmt.type)
        if type_name not in _ALLOWED_STMT_TYPES:
            raise ValueError(
                f"Statement type {type_name} not allowed: {stmt.query[:100]}"
            )
        # Block data exfiltration via SELECT … INTO or COPY (some DuckDB
        # versions parse COPY-to-file as SELECT-type).
        upper = stmt.query.upper()
        if " INTO " in upper or " COPY " in upper:
            raise ValueError(
                f"INTO/COPY not allowed (data exfiltration risk): {stmt.query[:100]}"
            )



def create_views(
    con: duckdb.DuckDBPyConnection,
    tables: list[dict],
    storage_root: str,
    tenant: str,
    storage_options: dict[str, Any],
) -> None:
    """Register each table as a DuckDB VIEW over delta_scan."""
    _configure_duckdb_s3(con, storage_options)
    for t in tables:
        dp = delta_path(t, storage_root, tenant)
        con.execute(f"CREATE VIEW {t['name']} AS SELECT * FROM delta_scan('{dp}')")


def query(
    sql: str,
    tables: list[dict],
    storage_root: str,
    tenant: str = "default",
    org_path: str | None = None,
    default_limit: int = 1000,
    storage_options: dict[str, Any] | None = None,
) -> pl.DataFrame:
    """
    Execute a read-only SQL query against Delta tables via DuckDB.

    Args:
        sql:            SELECT statement (table names must match config).
        tables:         Table definitions from config.
        storage_root:   Root path for delta tables (S3 URL).
        tenant:         Tenant subdirectory.
        org_path:       Optional org prefix for row-level security filter.
        default_limit:  Default LIMIT if not present in SQL.
        storage_options:  S3 credentials for DuckDB httpfs.

    Returns:
        Polars DataFrame with query results.
    """
    validate_sql(sql)

    so = storage_options or {}
    con = duckdb.connect()
    con.execute("SET statement_timeout='30s'")

    try:
        create_views(con, tables, storage_root, tenant, so)

        safe_sql = sql.rstrip().rstrip(";")
        if org_path:
            safe_sql += f" WHERE org_path LIKE '{org_path}%'"
        if "LIMIT" not in safe_sql.upper():
            safe_sql += f" LIMIT {default_limit}"

        result = con.execute(safe_sql).fetchdf()
        return pl.DataFrame(result)
    finally:
        con.close()


# ── Schema description generators (for SKILL.md / AI prompt) ────────

def generate_schema_description(tables: list[dict]) -> str:
    """
    Generate AI schema context from table configs.

    Used in generated SKILL.md and prompt.md.j2 so the AI
    knows available tables/columns without a separate discovery call.
    """
    lines: list[str] = []
    lines.append("You are a SQL generator. Available tables:\n")
    for t in tables:
        lines.append(f"Table: {t['name']} — {t['description']}")
        for f in t["fields"]:
            if f.get("generated"):
                continue
            lines.append(f"  - {f['name']} ({f['type']}): {f['description']}")
        lines.append("")
    lines.append("Rules:")
    lines.append("- Only generate SELECT statements")
    lines.append("- Do NOT include WHERE org_path — it will be auto-appended")
    lines.append("- Column names must match exactly as listed above")
    return "\n".join(lines)


def generate_skill_description(tables: list[dict]) -> str:
    """
    Generate a short human-readable description for the SKILL.md frontmatter.

    Example: "Query product sales and inventory data via natural language -> SQL"
    """
    table_names = ", ".join(t["name"] for t in tables)
    topics = ", ".join(t["description"] for t in tables)
    return f"Query {table_names} ({topics}) via natural language -> SQL on Delta Lake"
