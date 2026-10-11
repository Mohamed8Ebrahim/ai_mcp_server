from odoo import api, fields, models


class McpTokenReveal(models.TransientModel):
    _name = 'mcp.token.reveal'
    _description = 'MCP Token Reveal Wizard'

    token_id = fields.Many2one(
        'mcp.token', string='Token', required=True,
        help="The token whose freshly generated secret is being displayed.")
    raw_token = fields.Char(
        string='Secret Token', readonly=True,
        help="Your secret access token. Copy it now — for security it is stored "
             "only as a hash and cannot be shown again.")
    endpoint_url = fields.Char(
        string='Endpoint URL', compute='_compute_urls',
        help="Base MCP endpoint for clients that send an Authorization header "
             "(e.g. Claude Desktop, Cursor).")
    connector_url = fields.Char(
        string='Connector URL', compute='_compute_urls',
        help="Ready-to-paste URL with the token embedded, for clients that cannot "
             "send custom headers (e.g. the claude.ai web connector).")
    header_value = fields.Char(
        string='Authorization Header', compute='_compute_urls',
        help="The exact Authorization header value for header-based clients.")
    client_config = fields.Text(
        string='AI Client Config', compute='_compute_urls',
        help="Ready-to-paste MCP client configuration (via the mcp-remote bridge) with "
             "your endpoint and token already filled in — works with Claude Desktop, "
             "Cursor and any other MCP-compatible AI tool.")
    gemini_config = fields.Text(
        string='Gemini CLI Config', compute='_compute_urls',
        help="Ready-to-paste block for ~/.gemini/settings.json so Gemini CLI connects "
             "to this server over Streamable HTTP with the token as a header.")

    def _public_base_url(self):
        ICP = self.env['ir.config_parameter'].sudo()
        base = (ICP.get_param('m7_mcp_ai_connector.public_base_url')
                or ICP.get_param('web.base.url')
                or '')
        return base.rstrip('/')

    @api.depends('raw_token')
    def _compute_urls(self):
        base = self._public_base_url()
        dbname = self.env.cr.dbname
        for rec in self:
            token = rec.raw_token or ''
            # Include db name so multi-database hosts resolve without db_name in odoo.conf.
            rec.endpoint_url = '%s/mcp?db=%s' % (base, dbname)
            rec.connector_url = '%s/mcp/%s/%s' % (base, dbname, token)
            rec.header_value = 'Bearer %s' % token
            rec.client_config = (
                '{\n'
                '  "mcpServers": {\n'
                '    "odoo-mcp": {\n'
                '      "command": "npx",\n'
                '      "args": [\n'
                '        "-y", "mcp-remote@0.1.9",\n'
                '        "%s",\n'
                '        "--header", "Authorization: Bearer %s"\n'
                '      ]\n'
                '    }\n'
                '  }\n'
                '}'
            ) % (rec.endpoint_url, token)
            rec.gemini_config = (
                '{\n'
                '  "mcpServers": {\n'
                '    "odoo-mcp": {\n'
                '      "httpUrl": "%s",\n'
                '      "headers": {\n'
                '        "Authorization": "Bearer %s"\n'
                '      }\n'
                '    }\n'
                '  }\n'
                '}'
            ) % (rec.endpoint_url, token)
