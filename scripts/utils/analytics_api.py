"""
API sync and data ingestion.

Fetches data from HTTP APIs, writes to Delta Lake via delta_store.
Handles: HTTP calls, incremental since-tracking, response normalization.

Knows nothing about SQL, DuckDB, or query execution.
"""
from __future__ import annotations

import os
from typing import Any

import httpx
from pydantic_settings import BaseSettings, SettingsConfigDict

from . import delta_store


# ── Shared config (imported by skill run.py) ────────────────────────

class ApiConfig(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")
    base_url: str = "https://api.example.com"
    timeout: int = 30


class ContextSettings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")
    user_id: str = "CONTEXT_USER_ID"
    token: str = "CONTEXT_METADATA_ACCESS_TOKEN"


# ── HTTP fetch ──────────────────────────────────────────────────────

def fetch_api(
    base_url: str,
    endpoint: str,
    method: str = "GET",
    params: dict | None = None,
    timeout: int = 30,
) -> list[dict]:
    """
    Fetch data from an API endpoint and normalize to a list of records.

    Handles response unwrapping: extracts `data`, `items`, or `results` keys
    from dict responses, or wraps a single dict in a list.

    Returns:
        List of raw record dicts (API-field keys preserved).
    """
    method = method.upper()
    if method == "GET":
        resp = httpx.get(f"{base_url}{endpoint}", params=params, timeout=timeout)
    else:
        resp = httpx.post(f"{base_url}{endpoint}", json=params, timeout=timeout)
    resp.raise_for_status()

    data = resp.json()
    if isinstance(data, dict):
        data = data.get("data", data.get("items", data.get("results", [data])))
    if not isinstance(data, list):
        data = [data]
    return data


def sync_table(
    table_cfg: dict,
    base_url: str,
    storage_root: str,
    tenant: str = "default",
    generated_values: dict[str, str] | None = None,
    timeout: int = 30,
) -> int:
    """
    Sync a single table from API to Delta Lake (incremental).

    1. Opens or creates the Delta table from schema.
    2. Queries MAX(update_field) to determine `since` timestamp.
    3. Fetches API records (with `since` param if applicable).
    4. Writes records via delta_store.write_records().

    Args:
        table_cfg:       Table definition (api_endpoint, api_method, update_field, fields...).
        base_url:        API base URL.
        storage_root:    Root path for Delta tables.
        tenant:          Tenant subdirectory.
        generated_values: Dict of generated field name → value (e.g. {"org_path": "/a/b"}).
        timeout:         HTTP request timeout in seconds.

    Returns:
        Number of records written (0 if no new data).
    """
    path = delta_store.delta_path(table_cfg, storage_root, tenant)
    tbl = delta_store.open_or_create_table(table_cfg, path)

    # Determine incremental sync point
    since = None
    if delta_store.table_exists(path):
        since = delta_store.last_update(tbl, table_cfg["update_field"])

    # Build API request params
    params = dict(table_cfg.get("api_params", {}))
    if since:
        params["since"] = since

    # Fetch
    records = fetch_api(
        base_url=base_url,
        endpoint=table_cfg["api_endpoint"],
        method=table_cfg.get("api_method", "GET"),
        params=params,
        timeout=timeout,
    )

    # Write via generic store
    return delta_store.write_records(
        table_cfg=table_cfg,
        records=records,
        storage_root=storage_root,
        tenant=tenant,
        generated_values=generated_values,
    )


def sync_all_tables(
    tables: list[dict],
    base_url: str,
    storage_root: str,
    tenant: str = "default",
    generated_values: dict[str, str] | None = None,
    timeout: int = 30,
) -> dict[str, int]:
    """
    Sync all configured tables.

    Returns:
        Dict mapping table name → records written.
    """
    results = {}
    for t in tables:
        count = sync_table(t, base_url, storage_root, tenant, generated_values, timeout)
        results[t["name"]] = count
    return results


def resolve_generated_values(tables: list[dict], context: ContextSettings) -> dict[str, str]:
    """Scan table fields for generated values (e.g. org_path from env)."""
    result = {}
    for t in tables:
        for f in t.get("fields", []):
            if f.get("generated") and f["name"] == "org_path":
                user_id = os.environ.get(context.user_id, "default")
                result["org_path"] = f"/{user_id}/"
    return result


def sync_and_query(
    sql: str,
    tables: list[dict],
    base_url: str,
    storage_root: str,
    tenant: str = "default",
    context: ContextSettings | None = None,
    timeout: int = 30,
    default_limit: int = 1000,
) -> Any:
    """
    Convenience: sync all tables first, then execute a read-only SQL query.

    Args:
        sql:            SELECT statement.
        tables:         Table definitions from config.
        base_url:       API base URL (for sync).
        storage_root:   Root path for Delta tables.
        tenant:         Tenant subdirectory.
        context:        Context settings for generated value resolution.
        timeout:        HTTP request timeout.
        default_limit:  Default LIMIT if not present in SQL.

    Returns:
        Polars DataFrame with query results.
    """
    ctx = context or ContextSettings()
    generated = resolve_generated_values(tables, ctx) or None

    sync_all_tables(
        tables=tables,
        base_url=base_url,
        storage_root=storage_root,
        tenant=tenant,
        generated_values=generated,
        timeout=timeout,
    )

    return delta_store.query(
        sql=sql,
        tables=tables,
        storage_root=storage_root,
        tenant=tenant,
        org_path=generated.get("org_path") if generated else None,
        default_limit=default_limit,
    )
