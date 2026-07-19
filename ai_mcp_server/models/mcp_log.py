from datetime import timedelta

from odoo import api, fields, models


class McpLog(models.Model):
    _name = 'mcp.log'
    _description = 'MCP Audit Log'
    _order = 'create_date desc'
    _rec_name = 'tool_name'

    token_id = fields.Many2one(
        'mcp.token', string='Token', ondelete='cascade', index=True,
        help="The access token used for this MCP call.")
    user_id = fields.Many2one(
        'res.users', string='Acted As', index=True,
        help="The Odoo user the call was executed as.")
    method = fields.Char(
        string='JSON-RPC Method',
        help="The MCP JSON-RPC method invoked (e.g. tools/call, initialize).")
    tool_name = fields.Char(
        string='Tool', index=True,
        help="The MCP tool that was executed for this call.")
    model_name = fields.Char(
        string='Model', index=True,
        help="The Odoo model targeted by this call, when applicable.")
    arguments = fields.Text(
        string='Arguments',
        help="JSON snapshot of the arguments received for this call.")
    result_summary = fields.Char(
        string='Result Summary',
        help="Short summary of the outcome, such as the number of records returned "
             "or affected.")
    success = fields.Boolean(
        string='Success', default=True, index=True,
        help="Whether the call completed successfully.")
    error_message = fields.Text(
        string='Error',
        help="The error message captured when the call failed.")
    duration_ms = fields.Float(
        string='Duration (ms)',
        help="Server side execution time of the call in milliseconds.")
    client_ip = fields.Char(
        string='Client IP',
        help="IP address of the AI client that issued the call.")

    @api.model
    def _cron_purge_logs(self):
        """Scheduled cleanup of audit logs older than the configured retention."""
        days = self.env['ir.config_parameter'].sudo().get_param(
            'ai_mcp_server.log_retention_days', '90')
        try:
            days = int(days)
        except (TypeError, ValueError):
            days = 90
        if days <= 0:
            return  # 0 means keep logs forever
        cutoff = fields.Datetime.now() - timedelta(days=days)
        self.sudo().search([('create_date', '<', cutoff)]).unlink()
