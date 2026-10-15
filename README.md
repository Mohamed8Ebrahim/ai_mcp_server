# AI MCP Server — AI Connector for Odoo 19

`m7_mcp_ai_connector` turns an Odoo 19 database into a secure, self-hosted
[Model Context Protocol (MCP)](https://modelcontextprotocol.io) server. Claude,
ChatGPT, Cursor and any other MCP client can then read, analyze and update Odoo
data in natural language — governed by Odoo's own access rights and fully audited.

No Node.js, Redis or external bridge is required: the MCP endpoint is served
directly by Odoo at `/mcp`.

Tutorial video: https://youtu.be/TqjCfzd2948

## Features

- **Native MCP endpoint** — JSON-RPC 2.0 over Streamable HTTP (protocol `2024-11-05`),
  supporting `initialize`, `ping`, `tools/list`, `tools/call` and batch requests.
- **Personal access tokens** — revocable Bearer tokens with optional expiry. Only a
  SHA-256 hash is stored; the raw token is shown once at generation time.
- **Per-token governance** — scope (Read / Read & Write / Administrator), allowed
  models, allowed tools, IP allow-list and per-minute rate limit.
- **Runs as the token owner** — every call executes as the token's Odoo user, so
  ACLs and record rules apply unchanged.
- **Audit trail** — each call is logged (tool, model, arguments, result size,
  duration, client IP, success/error); old logs are purged by a daily cron.
- **Multi-database aware** — routes requests to the right database via
  `/mcp/<db>/<token>`, a `?db=` hint, or token lookup.
- **Arabic translation** included.

## Built-in tools

| Tool | Scope | Purpose |
|------|-------|---------|
| `odoo_search_read` | read | Search records and read fields in one call |
| `odoo_read` | read | Read fields of records by ID |
| `odoo_count` | read | Count records matching a domain |
| `odoo_name_search` | read | Fuzzy-search by display name to resolve IDs |
| `odoo_read_group` | read | Grouped aggregates (sum/avg/count) for analytics |
| `odoo_fields_get` | read | Field metadata for a model |
| `odoo_list_models` | read | Models the current user can access |
| `odoo_module_list` | read | Installed modules |
| `search` / `fetch` | read | ChatGPT connector / deep-research compatible search and fetch |
| `odoo_create` | write | Create a record |
| `odoo_write` | write | Update records by ID |
| `odoo_unlink` | write | Delete records by ID (irreversible) |
| `odoo_call_method` | admin | Call a business method (framework-level methods are blocked) |
| `odoo_db_size` | admin | Database size |
| `odoo_filestore_stats` | admin | Filestore statistics |
| `odoo_system_info` | admin | Server / system information |

Tools are defined in code (`services/tools.py`, `data/mcp_tool_data.xml`). The
**Tools** screen in Odoo can only enable or disable them, not add new ones.

## Installation

1. Copy `m7_mcp_ai_connector` into your Odoo 19 addons path.
2. Recommended for multi-database servers (or when `db_name` is not pinned):
   add the module to `server_wide_modules` so the database router is active at
   process start:

   ```ini
   [options]
   server_wide_modules = base,web,m7_mcp_ai_connector
   ```

3. Restart Odoo, update the apps list and install **AI MCP Server**.

Dependencies: `base`, `web`, `mail`. No extra Python packages.

## Configuration

**MCP Server → Configuration → Settings**

| Setting | Default | Description |
|---------|---------|-------------|
| Enable MCP Server | on | Master switch for the endpoint |
| Default Rate Limit | 120 calls/min | Applied to new tokens |
| Log Retention | 90 days | `0` keeps logs forever |
| Max Records Per Call | 200 | Hard cap on records returned by read tools |
| ChatGPT Searchable Models | partners, products, sales, purchases, CRM, invoices, tasks, pickings | Models scanned by the `search` tool |

The public URL shown in the UI comes from `m7_mcp_ai_connector.public_base_url`
(system parameter) or falls back to `web.base.url`. Public hosts are upgraded to
`https://` automatically, since clients such as claude.ai require HTTPS.

Access is controlled by two groups: **MCP User** (manages own tokens and logs) and
**MCP Administrator** (sees all tokens and logs).

## Connecting an AI client

1. Go to **MCP Server → AI Access Keys**, create a key, choose the user, scope and
   restrictions, then generate and copy the token.
2. Configure your client with one of these endpoints:

| Endpoint | Authentication | Use case |
|----------|----------------|----------|
| `POST /mcp` | `Authorization: Bearer <token>` (or `X-Api-Key`) | Claude Desktop, Cursor, scripts |
| `POST /mcp/<token>` | Token in URL | Clients that cannot send headers (e.g. claude.ai custom connectors) |
| `POST /mcp/<db>/<token>` | Token in URL + explicit database | Multi-database servers |
| `GET /mcp/health` | None | Health check (`?db=<name>` when several databases are hosted) |

Example:

```bash
curl -s https://odoo.example.com/mcp \
  -H "Authorization: Bearer $MCP_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'
```

> URLs that embed the token are secrets in themselves: anyone holding the URL has
> the token's access. Prefer the Bearer header when your client supports it.

## Monitoring

- **AI Access Keys** show live connection status, the connected client name and
  version, the last IP and total call count.
- **Audit Logs** list every MCP call with arguments, duration and errors.

## Module layout

```
m7_mcp_ai_connector/
├── controllers/   # /mcp HTTP endpoints, auth, CORS
├── services/      # MCP protocol, tool executor, multi-db router, URL helpers
├── models/        # mcp.token, mcp.tool, mcp.log, settings
├── wizard/        # one-time token reveal
├── views/ data/ security/ i18n/ static/
```

## Versions

This branch targets **Odoo 19**. Other Odoo versions live in the `13.0`, `17.0` and
`18.0` branches.

## License

OPL-1 (Odoo Proprietary License v1.0). Author: M7hm6d — support: 01274021065bk.bk@gmail.com
