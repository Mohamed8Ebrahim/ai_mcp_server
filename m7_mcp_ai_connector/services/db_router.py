# -*- coding: utf-8 -*-
"""Multi-database routing for the MCP endpoint (Odoo 13).

When several PostgreSQL databases share one Odoo HTTP process and ``db_name``
is not pinned in odoo.conf, Odoo cannot decide which registry to open, so
``/mcp/...`` falls into the nodb router and returns 404.

Odoo 13 selects the database in ``Root.setup_db`` (not
``Request._get_session_and_dbname``). This module patches that hook so MCP
requests select the database from:

1. An explicit path segment: ``/mcp/<db_name>/<token>``
2. A ``?db=`` query hint (combined with the Bearer / path token)
3. A scan of available databases for a matching ``mcp.token`` hash

The patch must be installed at process start via ``server_wide_modules``
(see ``post_load``) so it runs before the db / nodb dispatch decision.
"""
import hashlib
import logging
import threading
import time

from odoo.http import Root, db_list
from odoo.modules.registry import Registry

_logger = logging.getLogger(__name__)

# token_hash -> (dbname, monotonic_expiry)
_TOKEN_DB_CACHE = {}
_CACHE_LOCK = threading.Lock()
_CACHE_TTL_SECONDS = 300
_PATCHED = False
_ORIGINAL_SETUP_DB = None


def _hash_token(raw_token):
    return hashlib.sha256(raw_token.encode('utf-8')).hexdigest()


def _cache_get(token_hash):
    now = time.monotonic()
    with _CACHE_LOCK:
        entry = _TOKEN_DB_CACHE.get(token_hash)
        if not entry:
            return None
        dbname, expiry = entry
        if expiry < now:
            _TOKEN_DB_CACHE.pop(token_hash, None)
            return None
        return dbname


def _cache_set(token_hash, dbname):
    with _CACHE_LOCK:
        _TOKEN_DB_CACHE[token_hash] = (dbname, time.monotonic() + _CACHE_TTL_SECONDS)


def invalidate_token_db_cache(raw_token=None):
    """Drop cached db resolution (all entries, or one token)."""
    with _CACHE_LOCK:
        if raw_token is None:
            _TOKEN_DB_CACHE.clear()
            return
        _TOKEN_DB_CACHE.pop(_hash_token(raw_token.strip()), None)


def _token_exists_in_db(dbname, token_hash):
    """Return True if an active mcp.token row matches ``token_hash`` in ``dbname``."""
    try:
        registry = Registry(dbname)
    except Exception:  # noqa: BLE001 - skip unreadable / incompatible DBs
        _logger.debug("MCP db_router: cannot open registry for %s", dbname, exc_info=True)
        return False
    try:
        with registry.cursor() as cr:
            cr.execute(
                """
                SELECT 1
                  FROM information_schema.tables
                 WHERE table_schema = 'public'
                   AND table_name = 'mcp_token'
                 LIMIT 1
                """
            )
            if not cr.fetchone():
                return False
            cr.execute(
                """
                SELECT 1
                  FROM mcp_token
                 WHERE token_hash = %s
                   AND active IS TRUE
                 LIMIT 1
                """,
                (token_hash,),
            )
            return bool(cr.fetchone())
    except Exception:  # noqa: BLE001
        _logger.debug("MCP db_router: token probe failed on %s", dbname, exc_info=True)
        return False


def resolve_db_for_token(raw_token, hint_db=None, httprequest=None):
    """Return the database name that owns ``raw_token``, or None."""
    if not raw_token:
        return None
    raw_token = raw_token.strip()
    if not raw_token:
        return None

    token_hash = _hash_token(raw_token)
    cached = _cache_get(token_hash)
    if cached and (not hint_db or cached == hint_db):
        return cached

    try:
        available = set(db_list(True, httprequest))
    except Exception:  # noqa: BLE001
        _logger.debug("MCP db_router: db_list failed", exc_info=True)
        available = set()

    candidates = []
    if hint_db and hint_db in available:
        candidates.append(hint_db)
    for name in sorted(available):
        if name not in candidates:
            candidates.append(name)

    for dbname in candidates:
        if _token_exists_in_db(dbname, token_hash):
            _cache_set(token_hash, dbname)
            _logger.info("MCP db_router: token resolved to database %s", dbname)
            return dbname
    return None


def extract_mcp_db_and_token(httprequest):
    """Parse db hint + raw token from an MCP HTTP request.

    Supported shapes:
    - ``/mcp/<token>``
    - ``/mcp/<db_name>/<token>``
    - ``Authorization: Bearer <token>`` / ``X-Api-Key``
    - ``?db=<db_name>`` as an optional hint
    """
    path = (httprequest.path or '').rstrip('/')
    parts = [p for p in path.split('/') if p]
    hint_db = None
    token = None

    if parts and parts[0] == 'mcp':
        if len(parts) >= 3 and parts[1] != 'health':
            hint_db, token = parts[1], parts[2]
        elif len(parts) == 2 and parts[1] != 'health':
            token = parts[1]

    if not token:
        auth = httprequest.headers.get('Authorization', '') or ''
        if auth.lower().startswith('bearer '):
            token = auth[7:].strip() or None
        if not token:
            token = (httprequest.headers.get('X-Api-Key', '') or '').strip() or None

    query_db = (httprequest.args.get('db') or '').strip() or None
    if query_db:
        hint_db = hint_db or query_db

    return hint_db, token


def _patched_setup_db(self, httprequest):
    _ORIGINAL_SETUP_DB(self, httprequest)
    if httprequest.session.db:
        return

    path = httprequest.path or ''
    if not path.startswith('/mcp'):
        return

    hint_db, token = extract_mcp_db_and_token(httprequest)

    # Fast path: explicit db in URL (/mcp/<db>/<token> or ?db=...).
    if hint_db:
        try:
            if hint_db in db_list(True, httprequest):
                httprequest.session.db = hint_db
                if token:
                    _cache_set(_hash_token(token), hint_db)
                return
        except Exception:  # noqa: BLE001
            _logger.debug("MCP db_router: hint db check failed", exc_info=True)
        return

    if not token:
        return

    resolved = resolve_db_for_token(token, hint_db=None, httprequest=httprequest)
    if resolved:
        httprequest.session.db = resolved


def install_db_router():
    """Idempotently monkey-patch Odoo 13 DB selection for /mcp."""
    global _PATCHED, _ORIGINAL_SETUP_DB
    if _PATCHED:
        return
    _ORIGINAL_SETUP_DB = Root.setup_db
    Root.setup_db = _patched_setup_db
    _PATCHED = True
    _logger.info(
        "MCP db_router installed (Odoo 13) — multi-database /mcp requests "
        "resolve the database from the access token (or /mcp/<db>/<token>).")
