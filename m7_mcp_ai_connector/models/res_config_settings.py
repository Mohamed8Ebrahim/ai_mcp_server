from odoo import api, fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    mcp_server_enabled = fields.Boolean(
        string='Enable MCP Server',
        config_parameter='m7_mcp_ai_connector.enabled', default=True,
        help="Master switch that turns the MCP endpoint on or off for the whole "
             "database.")
    mcp_default_rate_limit = fields.Integer(
        string='Default Rate Limit (calls/min)',
        config_parameter='m7_mcp_ai_connector.default_rate_limit', default=120,
        help="Default per-minute call limit applied to newly created tokens.")
    mcp_log_retention_days = fields.Integer(
        string='Log Retention (days)',
        config_parameter='m7_mcp_ai_connector.log_retention_days', default=90,
        help="Number of days audit logs are kept before automatic cleanup. Set to "
             "0 to keep logs forever.")
    mcp_max_records = fields.Integer(
        string='Max Records Per Call',
        config_parameter='m7_mcp_ai_connector.max_records', default=200,
        help="Hard cap on the number of records any single read tool may return, "
             "protecting the server from oversized responses.")
    mcp_endpoint_url = fields.Char(
        string='Endpoint URL', compute='_compute_endpoint_url',
        help="The MCP endpoint URL to configure inside your AI client.")

    def _compute_endpoint_url(self):
        # base = self.env['ir.config_parameter'].sudo().get_param('web.base.url', '')
        base = 'https://kamron-heroic-dorie.ngrok-free.dev'
        for rec in self:
            rec.mcp_endpoint_url = (base or '').rstrip('/') + '/mcp'
