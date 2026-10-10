from odoo import api, fields, models, _
from odoo.exceptions import UserError


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
    # Named `enabled` (not `active`) on purpose: Odoo's `active` field auto-hides
    # archived rows from search(), which previously let disabled tools keep working.
    enabled = fields.Boolean(
        string='Enabled', default=True,
        help="Globally enable or disable this tool for every token. Disabled tools "
             "are hidden from the AI client's tool list. This is the only field "
             "editable from the interface.")

    _sql_constraints = [
        ('technical_name_uniq', 'unique(technical_name)',
         'The tool technical name must be unique.'),
    ]

    def _is_module_data_load(self):
        return bool(
            self.env.context.get('install_module')
            or self.env.context.get('module')
        )

    @api.model_create_multi
    def create(self, vals_list):
        if not self._is_module_data_load():
            raise UserError(_(
                "MCP tools are defined in code and cannot be created from the "
                "interface. Add them in the module sources and upgrade the app."
            ))
        return super().create(vals_list)

    def write(self, vals):
        if self._is_module_data_load():
            return super().write(vals)
        # Only Enabled may be toggled from the UI / RPC.
        if set(vals) - {'enabled'}:
            raise UserError(_(
                "Only the Enabled flag can be changed from the interface. "
                "Other tool fields are managed in the module code."
            ))
        return super().write(vals)

    def unlink(self):
        if not self._is_module_data_load():
            raise UserError(_(
                "MCP tools cannot be deleted from the interface. "
                "Remove them from the module sources and upgrade the app."
            ))
        return super().unlink()
