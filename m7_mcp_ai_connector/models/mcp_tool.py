from odoo import fields, models


class McpTool(models.Model):
    _name = 'mcp.tool'
    _description = 'MCP Tool Registry'
    _order = 'sequence, technical_name'

    sequence = fields.Integer(
        string='Sequence', default=10,
        help="Display order of the tool in the registry list.")
    name = fields.Char(
        string='Tool Label', required=True,
        help="Human friendly name of the MCP tool shown to administrators.")
    technical_name = fields.Char(
        string='Tool Name', required=True, index=True,
        help="The exact tool identifier exposed to the AI client over MCP "
             "(e.g. 'odoo_search_read'). Must be unique.")
    description = fields.Text(
        string='Description',
        help="Natural language description sent to the AI client so it knows when "
             "and how to use this tool.")
    required_scope = fields.Selection(
        selection=[
            ('read', 'Read'),
            ('write', 'Write'),
            ('admin', 'Admin'),
        ], string='Required Scope', default='read', required=True,
        help="Minimum token scope needed to invoke this tool.")
    active = fields.Boolean(
        string='Enabled', default=True,
        help="Globally enable or disable this tool for every token. Disabled tools "
             "are hidden from the AI client's tool list.")

    _sql_constraints = [
        ('technical_name_uniq', 'unique(technical_name)',
         'The tool technical name must be unique.'),
    ]
