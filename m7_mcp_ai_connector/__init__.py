from . import models
from . import services
from . import wizard
from . import controllers

# Install as soon as this package is imported (first registry that has the
# module loaded on a worker). For cold multi-db requests before any registry
# exists, also declare post_load and list the module in server_wide_modules.
try:
    from .services.db_router import install_db_router
    install_db_router()
except Exception:  # noqa: BLE001 - never block module import on patch failure
    import logging
    logging.getLogger(__name__).exception(
        "MCP db_router: failed to install multi-database patch on import")


def post_load():
    """Called at process start when the module is in server_wide_modules."""
    from .services.db_router import install_db_router
    install_db_router()
