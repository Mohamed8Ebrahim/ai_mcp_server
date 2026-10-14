# -*- coding: utf-8 -*-
"""Public base URL helpers for MCP connector links."""

import ipaddress
from urllib.parse import urlparse

_LOCAL_HOSTS = frozenset({'localhost', '127.0.0.1', '::1'})
_LOCAL_SUFFIXES = ('.local', '.lan', '.internal', '.home', '.corp')


def _parse_host(base):
    """Return (host, port) from a base URL string, lowercased host."""
    if not base:
        return '', None
    if '://' not in base:
        base = 'http://' + base
    parsed = urlparse(base)
    host = (parsed.hostname or '').lower()
    return host, parsed.port


def _host_is_private_ip(host):
    try:
        return ipaddress.ip_address(host).is_private
    except ValueError:
        return False


def is_local_url(base):
    """Return True when ``base`` points at a local / private / machine host.

    Local examples:
    - localhost, 127.0.0.1, ::1
    - 192.168.x.x / 10.x.x.x (private IP)
    - bare hostname without a domain (e.g. m7ham6d-hp-zbook-...)
    - *.local / *.lan / *.internal

    Online examples:
    - epico.cloud
    - kamron-….ngrok-free.dev
    - odoo.example.com
    """
    host, _port = _parse_host(base)
    if not host:
        return True
    if host in _LOCAL_HOSTS:
        return True
    if any(host.endswith(suf) for suf in _LOCAL_SUFFIXES):
        return True
    if _host_is_private_ip(host):
        return True
    # Machine name only — no public domain label.
    if '.' not in host:
        return True
    return False


def is_online_url(base):
    """Return True when ``base`` looks like a public online host / tunnel."""
    return bool(base) and not is_local_url(base)


def get_public_base_url(env):
    """Return the public site root used in MCP connector / endpoint URLs.

    Priority:
    1. ``m7_mcp_ai_connector.public_base_url`` (explicit module override)
    2. ``web.base.url`` (what the admin configured — ngrok, cloud domain, …)

    Upgrade ``http://`` → ``https://`` only for online hosts (Claude.ai and
    similar require HTTPS). Local / private hosts keep ``http://``.
    """
    ICP = env['ir.config_parameter'].sudo()
    base = (
        ICP.get_param('m7_mcp_ai_connector.public_base_url')
        or ICP.get_param('web.base.url')
        or ''
    ).rstrip('/')
    if base.startswith('http://') and is_online_url(base):
        base = 'https://' + base[len('http://'):]
    return base
