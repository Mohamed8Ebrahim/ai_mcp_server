{
    'name': 'AI MCP Server — AI Connector for Odoo',
    'version': '19.0.2.0.0',
    'category': 'Tools/Productivity',
    'summary': 'Turn Odoo into a secure Model Context Protocol (MCP) server so Claude, ChatGPT, Gemini and other AI assistants can safely read, analyze and update your database.',
    'description': """
AI MCP Server — AI Connector for Odoo
===========================================

Expose your Odoo database to Claude, ChatGPT, Cursor and any Model Context Protocol (MCP) compatible client through a single, secure, self-hosted endpoint — no Node.js, no Redis, no external bridge required.

Key Features
------------

* Native MCP Endpoint: a fully compliant JSON-RPC 2.0 / Streamable-HTTP server built straight into Odoo at /mcp.
* Personal Access Tokens: credential-free, revocable Bearer tokens with expiry dates, so no user password ever leaves your server.
* Fine-Grained Governance: per-token scopes (Read / Write / Admin), model allow-lists, IP allow-lists and per-minute rate limiting.
* Rich Tool-Set: search_read, read, count, name_search, read_group analytics, fields_get, list_models, create, write, unlink and safe method execution.
* Human-in-the-Loop Safety: write and delete operations honour Odoo's own access rights and record rules, executed strictly as the token owner.
* Complete Audit Trail: every MCP call is logged with tool, model, arguments, result size, duration, client IP and success/error state.
* Zero-Config Discovery: a health endpoint and capabilities handshake make connection setup a copy-paste affair.

Business Benefits
-----------------

* Let your team query and manage Odoo in natural language, safely.
* Replace ad-hoc SQL and manual exports with governed, audited AI access.
* Keep full control: revoke a token, tighten a scope, or lock an IP in seconds.
* Enterprise-grade traceability for every AI-driven data operation.
""",
    'author': 'M7hm6d',
    'support': '01274021065bk.bk@gmail.com',
    'images': ['static/description/banner.gif'],
    'price': 65.0,
    'currency': 'USD',
    'depends': ['base', 'web', 'mail'],
    'external_dependencies': {'python': []},
    'data': [
        'security/mcp_security.xml',
        'security/ir.model.access.csv',
        'data/mcp_tool_data.xml',
        'data/mcp_cron.xml',
        'wizard/mcp_token_reveal_views.xml',
        'views/mcp_token_views.xml',
        'views/mcp_tool_views.xml',
        'views/mcp_log_views.xml',
        'views/res_config_settings_views.xml',
        'views/mcp_menus.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'm7_mcp_ai_connector/static/src/scss/mcp_backend.scss',
            'm7_mcp_ai_connector/static/src/js/mcp_status_pill.js',
            'm7_mcp_ai_connector/static/src/js/mcp_copy.js',
            'm7_mcp_ai_connector/static/src/xml/mcp_status_pill.xml',
        ],
        # Loaded ONLY in dark mode — repaints light-only text/surface colours
        # so the light theme stays exactly as-is.
        'web.assets_web_dark': [
            'm7_mcp_ai_connector/static/src/scss/mcp_backend.dark.scss',
        ],
    },
    'installable': True,
    'application': True,
    'auto_install': False,
    'license': 'OPL-1',
}
