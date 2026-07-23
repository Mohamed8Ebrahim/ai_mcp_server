import hashlib
import secrets
import logging
from datetime import timedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)

# Ordered from least to most privileged so we can compare with index().
SCOPE_ORDER = ['read', 'write', 'admin']

# Minutes since the last successful call within which a token is still
# considered "connected/active". Older than this → idle/disconnected.
DEFAULT_ACTIVE_WINDOW_MINUTES = 15


class McpToken(models.Model):
    _name = 'mcp.token'
    _description = 'MCP Personal Access Token'
    _inherit = ['mail.thread']
    _order = 'create_date desc'

    name = fields.Char(
        string='Token Name', required=True, tracking=True,
        help="A human friendly label to identify where this access token is used "
             "(e.g. 'Claude Desktop - Ahmed').")
    user_id = fields.Many2one(
        'res.users', string='Acts As User', required=True,
        default=lambda self: self.env.user, tracking=True,
        help="Every MCP call made with this token executes strictly as this Odoo "
             "user, honouring all of that user's access rights and record rules.")
    token_hash = fields.Char(
        string='Token Hash', index=True, copy=False,
        help="Irreversible SHA-256 hash of the secret token used to authenticate "
             "incoming requests; the raw token is never stored.")
    token_preview = fields.Char(
        string='Token Preview', readonly=True, copy=False,
        help="A masked preview of the secret token showing only its last "
             "characters for identification.")
    scope = fields.Selection(
        selection=[
            ('read', 'Read Only'),
            ('write', 'Read & Write'),
            ('admin', 'Administrator'),
        ], string='Scope', default='read', required=True, tracking=True,
        help="Permission level granted to this token: Read Only allows queries "
             "only; Read & Write allows create/update/delete; Administrator also "
             "allows executing model methods.")
    active = fields.Boolean(
        string='Active', default=True, tracking=True,
        help="Uncheck to instantly revoke this token; revoked tokens are rejected "
             "on every request.")
    expiration_date = fields.Datetime(
        string='Expiration Date', tracking=True,
        help="Optional date and time after which this token stops working. Leave "
             "empty for a token that never expires.")
    model_ids = fields.Many2many(
        'ir.model', 'mcp_token_model_rel', 'token_id', 'model_id',
        string='Allowed Models',
        help="Restrict this token to these models only. Leave empty to allow every "
             "model the acting user can already access.")
    tool_ids = fields.Many2many(
        'mcp.tool', 'mcp_token_tool_rel', 'token_id', 'tool_id',
        string='Allowed Tools',
        help="Restrict this token to these MCP tools only. Leave empty to expose "
             "every globally enabled tool.")
    ip_allowlist = fields.Char(
        string='IP Allow-List',
        help="Optional comma separated list of client IP addresses permitted to "
             "use this token. Leave empty to allow any origin.")
    rate_limit = fields.Integer(
        string='Rate Limit (calls/min)', default=120,
        help="Maximum number of MCP calls allowed with this token per rolling "
             "minute. Set to 0 to disable rate limiting.")
    call_count = fields.Integer(
        string='Total Calls', readonly=True, copy=False,
        help="Lifetime number of MCP calls served with this token.")
    last_used = fields.Datetime(
        string='Last Used', readonly=True, copy=False,
        help="Timestamp of the most recent successful use of this token.")
    last_ip = fields.Char(
        string='Last IP', readonly=True, copy=False,
        help="Client IP address recorded on the most recent use of this token.")
    log_ids = fields.One2many(
        'mcp.log', 'token_id', string='Audit Logs',
        help="Full history of MCP calls performed with this token.")
    log_count = fields.Integer(
        string='Log Count', compute='_compute_log_count',
        help="Number of audit log entries recorded for this token.")
    is_expired = fields.Boolean(
        string='Expired', compute='_compute_is_expired',
        help="Indicates whether this token has passed its expiration date.")
    connection_state = fields.Selection(
        selection=[
            ('disabled', 'Server Disabled'),
            ('revoked', 'Revoked'),
            ('draft', 'Not Generated'),
            ('expired', 'Expired'),
            ('never', 'Awaiting First Connection'),
            ('active', 'Connected'),
            ('idle', 'Idle / Disconnected'),
        ], string='Connection Status', compute='_compute_connection_state',
        help="Live status of this token derived from real evidence — whether the "
             "MCP server is on, the token is generated/valid, and how recently it "
             "was actually used:\n"
             "• Server Disabled — the whole MCP server is switched off.\n"
             "• Revoked — this token was manually revoked.\n"
             "• Not Generated — no secret has been generated yet, so it cannot "
             "authenticate.\n"
             "• Expired — the token passed its expiration date.\n"
             "• Awaiting First Connection — ready, but never used yet.\n"
             "• Connected — used successfully within the active window.\n"
             "• Idle / Disconnected — used before, but not recently.")
    endpoint_url = fields.Char(
        string='MCP Endpoint', compute='_compute_endpoint_url',
        help="The base MCP endpoint URL of this server; the full secret is only "
             "shown once when you generate the token.")

    def _compute_endpoint_url(self):
        base = (self.env['ir.config_parameter'].sudo().get_param('web.base.url', '') or '').rstrip('/')
        for rec in self:
            rec.endpoint_url = base + '/mcp'

    def _compute_log_count(self):
        data = self.env['mcp.log']._read_group(
            [('token_id', 'in', self.ids)], ['token_id'], ['__count'])
        mapped = {token.id: count for token, count in data}
        for rec in self:
            rec.log_count = mapped.get(rec.id, 0)

    def _compute_is_expired(self):
        now = fields.Datetime.now()
        for rec in self:
            rec.is_expired = bool(rec.expiration_date and rec.expiration_date < now)

    def _server_enabled(self):
        param = self.env['ir.config_parameter'].sudo().get_param(
            'm7_mcp_ai_connector.enabled', 'True')
        return str(param).lower() not in ('false', '0', '')

    def _active_window_minutes(self):
        param = self.env['ir.config_parameter'].sudo().get_param(
            'm7_mcp_ai_connector.active_window_minutes', DEFAULT_ACTIVE_WINDOW_MINUTES)
        try:
            return int(param)
        except (TypeError, ValueError):
            return DEFAULT_ACTIVE_WINDOW_MINUTES

    @api.depends('active', 'token_hash', 'expiration_date', 'last_used')
    def _compute_connection_state(self):
        # Evaluated most-blocking first so the label always names the single
        # real reason the token is (or isn't) working right now. Time-based, so
        # this field is intentionally non-stored and recomputed on every read.
        now = fields.Datetime.now()
        server_on = self._server_enabled()
        window = timedelta(minutes=self._active_window_minutes())
        for rec in self:
            if not server_on:
                rec.connection_state = 'disabled'
            elif not rec.active:
                rec.connection_state = 'revoked'
            elif not rec.token_hash:
                rec.connection_state = 'draft'
            elif rec.expiration_date and rec.expiration_date < now:
                rec.connection_state = 'expired'
            elif not rec.last_used:
                rec.connection_state = 'never'
            elif rec.last_used >= now - window:
                rec.connection_state = 'active'
            else:
                rec.connection_state = 'idle'

    # ------------------------------------------------------------------
    # Token lifecycle
    # ------------------------------------------------------------------
    @staticmethod
    def _hash_token(raw_token):
        return hashlib.sha256(raw_token.encode('utf-8')).hexdigest()

    def _generate_raw_token(self):
        """Create a fresh secret, store only its hash + preview, return the raw."""
        self.ensure_one()
        raw = 'mcp_' + secrets.token_urlsafe(32)
        self.write({
            'token_hash': self._hash_token(raw),
            'token_preview': '****' + raw[-6:],
        })
        return raw

    @api.model_create_multi
    def create(self, vals_list):
        default_limit = self.env['ir.config_parameter'].sudo().get_param(
            'm7_mcp_ai_connector.default_rate_limit')
        for vals in vals_list:
            if default_limit and not vals.get('rate_limit'):
                try:
                    vals['rate_limit'] = int(default_limit)
                except (TypeError, ValueError):
                    pass
        return super().create(vals_list)

    def _open_reveal_wizard(self, raw):
        wizard = self.env['mcp.token.reveal'].create({
            'token_id': self.id,
            'raw_token': raw,
        })
        return {
            'type': 'ir.actions.act_window',
            'name': _('Your MCP Access Token'),
            'res_model': 'mcp.token.reveal',
            'res_id': wizard.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_reveal_token(self):
        """Generate a fresh secret and display it once. A secret can never be
        shown again, so generating always produces a brand-new token that
        supersedes any previous one."""
        self.ensure_one()
        already_had = bool(self.token_hash)
        raw = self._generate_raw_token()
        if already_had:
            self.message_post(body=_("A new secret token was generated. The previous token is now invalid."))
        return self._open_reveal_wizard(raw)

    def action_regenerate(self):
        """Invalidate the old secret and issue a new one."""
        self.ensure_one()
        raw = self._generate_raw_token()
        self.message_post(body=_("The secret token was regenerated. The previous token is now invalid."))
        return self._open_reveal_wizard(raw)

    def action_revoke(self):
        self.write({'active': False})

    def action_view_logs(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Audit Logs'),
            'res_model': 'mcp.log',
            'view_mode': 'list,form',
            'domain': [('token_id', '=', self.id)],
            'context': {'default_token_id': self.id},
        }

    # ------------------------------------------------------------------
    # Authentication & governance (called by the controller)
    # ------------------------------------------------------------------
    @api.model
    def _authenticate(self, raw_token, client_ip=None):
        """Return a validated token record (sudo) or raise a UserError."""
        if not raw_token:
            raise UserError(_("Missing Bearer token."))
        token_hash = self._hash_token(raw_token.strip())
        token = self.sudo().search([('token_hash', '=', token_hash)], limit=1)
        if not token:
            raise UserError(_("Invalid access token."))
        if not token.active:
            raise UserError(_("This access token has been revoked."))
        if token.expiration_date and token.expiration_date < fields.Datetime.now():
            raise UserError(_("This access token has expired."))
        if token.ip_allowlist and client_ip:
            allowed = [ip.strip() for ip in token.ip_allowlist.split(',') if ip.strip()]
            if allowed and client_ip not in allowed:
                raise UserError(_("Client IP %s is not allowed for this token.") % client_ip)
        token._check_rate_limit()
        return token

    def _check_rate_limit(self):
        self.ensure_one()
        if not self.rate_limit:
            return
        window_start = fields.Datetime.now() - timedelta(minutes=1)
        recent = self.env['mcp.log'].sudo().search_count([
            ('token_id', '=', self.id),
            ('create_date', '>=', window_start),
        ])
        if recent >= self.rate_limit:
            raise UserError(_("Rate limit exceeded (%s calls/min). Please slow down.") % self.rate_limit)

    def _check_scope(self, required_scope):
        self.ensure_one()
        if SCOPE_ORDER.index(self.scope) < SCOPE_ORDER.index(required_scope):
            raise UserError(_(
                "This token's scope '%s' is insufficient; '%s' is required.")
                % (self.scope, required_scope))

    def _check_model_allowed(self, model_name):
        self.ensure_one()
        if self.model_ids and model_name not in self.model_ids.mapped('model'):
            raise UserError(_("Model '%s' is not permitted for this token.") % model_name)

    def _check_tool_allowed(self, tool_name):
        self.ensure_one()
        if self.tool_ids and tool_name not in self.tool_ids.mapped('technical_name'):
            raise UserError(_("Tool '%s' is not permitted for this token.") % tool_name)

    def _register_use(self, client_ip=None):
        self.ensure_one()
        self.sudo().write({
            'call_count': self.call_count + 1,
            'last_used': fields.Datetime.now(),
            'last_ip': client_ip or self.last_ip,
        })

    def _touch(self, client_ip=None):
        """Record connection-level activity (handshake, tools listing, ping)
        without counting it as a billable tool call. This keeps the live
        Connection Status accurate the moment a client connects, not only when
        it first invokes a tool."""
        self.ensure_one()
        self.sudo().write({
            'last_used': fields.Datetime.now(),
            'last_ip': client_ip or self.last_ip,
        })
