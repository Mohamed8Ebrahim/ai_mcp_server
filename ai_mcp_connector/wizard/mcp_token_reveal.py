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

    @api.depends('raw_token')
    def _compute_urls(self):
        base = (self.env['ir.config_parameter'].sudo().get_param('web.base.url', '') or '').rstrip('/')
        for rec in self:
            token = rec.raw_token or ''
            rec.endpoint_url = base + '/mcp'
            rec.connector_url = '%s/mcp/%s' % (base, token)
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
