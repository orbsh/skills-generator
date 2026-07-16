"""PyIceberg helpers for Lakekeeper REST catalog + S3-compatible OSS."""

from __future__ import annotations

import os

from pyiceberg.catalog.rest import RestCatalog
from pyiceberg.io import (
    S3_ACCESS_KEY_ID,
    S3_ENDPOINT,
    S3_FORCE_VIRTUAL_ADDRESSING,
    S3_REGION,
    S3_SECRET_ACCESS_KEY,
)
from pyiceberg.io.pyarrow import PyArrowFileIO
from pyiceberg.table import Table


def ensure_oss_s3_compat_env() -> None:
    os.environ.setdefault("AWS_REQUEST_CHECKSUM_CALCULATION", "when_required")
    os.environ.setdefault("AWS_RESPONSE_CHECKSUM_VALIDATION", "when_required")


def oss_file_io_properties(
    *,
    region: str,
    endpoint: str,
    access_key: str,
    secret_key: str,
    extra: dict[str, str] | None = None,
) -> dict[str, str]:
    props = {
        S3_ENDPOINT: endpoint,
        S3_REGION: region,
        S3_ACCESS_KEY_ID: access_key,
        S3_SECRET_ACCESS_KEY: secret_key,
        S3_FORCE_VIRTUAL_ADDRESSING: "true",
        "s3.path-style-access": "false",
    }
    if extra:
        props.update(extra)
    props[S3_FORCE_VIRTUAL_ADDRESSING] = "true"
    props["s3.path-style-access"] = "false"
    return props


def load_rest_catalog(
    *,
    catalog_uri: str,
    warehouse: str,
    region: str,
    endpoint: str,
    access_key: str,
    secret_key: str,
    name: str = "lakekeeper",
) -> RestCatalog:
    if not access_key or not secret_key:
        raise ValueError("缺少 OSS 访问凭证（access_key / secret_key）")

    os.environ["AWS_ACCESS_KEY_ID"] = access_key
    os.environ["AWS_SECRET_ACCESS_KEY"] = secret_key
    os.environ["AWS_REGION"] = region
    os.environ["AWS_ENDPOINT_URL"] = endpoint
    ensure_oss_s3_compat_env()

    s3_props = oss_file_io_properties(
        region=region,
        endpoint=endpoint,
        access_key=access_key,
        secret_key=secret_key,
    )

    return RestCatalog(
        name,
        uri=catalog_uri.rstrip("/") + "/",
        warehouse=warehouse,
        **{
            "client.access-key-id": access_key,
            "client.secret-access-key": secret_key,
            "client.region": region,
            **s3_props,
        },
    )


def patch_table_pyarrow_io(
    table: Table,
    *,
    region: str,
    endpoint: str,
    access_key: str,
    secret_key: str,
    catalog_properties: dict[str, str] | None = None,
) -> Table:
    """Use PyArrow S3FileSystem for OSS reads (s3fs defaults miss endpoint)."""
    props = oss_file_io_properties(
        region=region,
        endpoint=endpoint,
        access_key=access_key,
        secret_key=secret_key,
        extra={**(catalog_properties or {}), **table.metadata.properties},
    )
    table.io = PyArrowFileIO(props)
    return table


def load_iceberg_table(
    catalog: RestCatalog,
    identifier: str,
    *,
    region: str,
    endpoint: str,
    access_key: str,
    secret_key: str,
) -> Table:
    table = catalog.load_table(identifier)
    return patch_table_pyarrow_io(
        table,
        region=region,
        endpoint=endpoint,
        access_key=access_key,
        secret_key=secret_key,
        catalog_properties=dict(catalog.properties),
    )
