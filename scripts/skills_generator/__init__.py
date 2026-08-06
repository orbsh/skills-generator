from .renderer import BaseComponent
from .components import (
    StatusComponent,
    SectionComponent,
    CodeBlockComponent,
    AlertComponent,
    KeyValueComponent,
)
from skillforge.logging import setup_logging, logger
from .errors import ExitCode, raise_exit, ensure_config, handle_httpx_errors

from .http import (
    HTTPClient,
    AsyncHTTPClient,
    create_client,
    create_async_client,
)
from .config import get_skill_root, build_settings_class, Settings, load_settings

# Iceberg — optional dependency (pyiceberg)
try:
    from .iceberg import (
        ensure_oss_s3_compat_env,
        oss_file_io_properties,
        load_rest_catalog,
        patch_table_pyarrow_io,
        load_iceberg_table,
    )
except ImportError:
    pass

__all__ = [
    # Renderer & Components
    "BaseComponent",
    "StatusComponent",
    "SectionComponent",
    "CodeBlockComponent",
    "AlertComponent",
    "KeyValueComponent",
    # Logging
    "setup_logging",
    "logger",
    # Errors
    "ExitCode",
    "raise_exit",
    "ensure_config",
    "handle_httpx_errors",
    # HTTP
    "HTTPClient",
    "AsyncHTTPClient",
    "create_client",
    "create_async_client",
    # Config
    "get_skill_root",
    "build_settings_class",
    "Settings",
    "load_settings",
    # Iceberg / Lakekeeper
    "ensure_oss_s3_compat_env",
    "oss_file_io_properties",
    "load_rest_catalog",
    "patch_table_pyarrow_io",
    "load_iceberg_table",
]
