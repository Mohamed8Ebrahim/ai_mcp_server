import json
import logging

from odoo import http, _
from odoo.http import request
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

CORS_HEADERS = [
    ('Access-Control-Allow-Origin', '*'),
    ('Access-Control-Allow-Methods', 'POST, GET, OPTIONS'),
    ('Access-Control-Allow-Headers', 'Content-Type, Authorization, Mcp-Session-Id, Mcp-Protocol-Version'),
    ('Access-Control-Max-Age', '86400'),
]


class McpController(http.Controller):

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _json_response(payload, status=200):
        body = json.dumps(payload, default=str, ensure_ascii=False)
        headers = [('Content-Type', 'application/json; charset=utf-8')] + CORS_HEADERS
        return request.make_response(body, headers=headers, status=status)

    @staticmethod
    def _client_ip():
        req = request.httprequest
        fwd = req.headers.get('X-Forwarded-For')
        if fwd:
            return fwd.split(',')[0].strip()
        return req.remote_addr

    @staticmethod
    def _bearer_token():
        auth = request.httprequest.headers.get('Authorization', '')
        if auth.lower().startswith('bearer '):
            return auth[7:].strip()
        # Fallback: some clients send the key via a dedicated header.
        return request.httprequest.headers.get('X-Api-Key', '').strip() or None

    def _server_enabled(self):
        param = request.env['ir.config_parameter'].sudo().get_param(
            'm7_mcp_ai_connector.enabled', 'True')
        return str(param).lower() not in ('false', '0', '')

    # ------------------------------------------------------------------
    # Shared request handler
    # ------------------------------------------------------------------
    def _handle(self, raw_token):
        # 1. Master switch
        if not self._server_enabled():
            return self._json_response(
                {'jsonrpc': '2.0', 'id': None,
                 'error': {'code': -32000, 'message': 'MCP server is disabled.'}}, status=503)

        # 2. Parse the JSON-RPC body (single object or batch array)
        try:
            raw = request.httprequest.get_data(as_text=True)
            payload = json.loads(raw) if raw else {}
        except (ValueError, TypeError):
            return self._json_response(
                {'jsonrpc': '2.0', 'id': None,
                 'error': {'code': -32700, 'message': 'Parse error.'}}, status=400)

        client_ip = self._client_ip()

        # 3. Authenticate the token
        try:
            token = request.env['mcp.token'].sudo()._authenticate(raw_token, client_ip)
        except UserError as e:
            return self._json_response(
                {'jsonrpc': '2.0', 'id': None,
                 'error': {'code': -32001, 'message': str(e)}}, status=401)

        # 4. Build an environment acting strictly as the token owner. Tool
        #    execution runs under this user so Odoo ACLs/record rules apply,
        #    while `token` stays a sudo record for governance reads.
        user_env = request.env(user=token.user_id.id)
        proto = user_env['mcp.protocol']

        # 5. Dispatch — support both a single message and a batch
        is_batch = isinstance(payload, list)
        messages = payload if is_batch else [payload]
        responses = []
        for message in messages:
            resp = proto.handle_message(message, token, client_ip)
            if resp is not None:
                responses.append(resp)

        # Notifications only → 202 Accepted, no body
        if not responses:
            return request.make_response('', headers=CORS_HEADERS, status=202)

        result = responses if is_batch else responses[0]
        return self._json_response(result, status=200)

    # ------------------------------------------------------------------
    # Endpoints
    # ------------------------------------------------------------------
    @http.route(['/mcp', '/mcp/<string:path_token>'], type='http', auth='none',
                methods=['OPTIONS'], csrf=False, save_session=False)
    def mcp_preflight(self, path_token=None, **kw):
        return request.make_response('', headers=CORS_HEADERS, status=204)

    @http.route('/mcp/health', type='http', auth='none', methods=['GET'], csrf=False, save_session=False)
    def mcp_health(self, **kw):
        return self._json_response({
            'status': 'ok' if self._server_enabled() else 'disabled',
            'server': 'Odoo MCP Server',
            'transport': 'streamable-http',
            'protocol': '2024-11-05',
        })

    @http.route('/mcp', type='http', auth='none', methods=['POST'], csrf=False, save_session=False)
    def mcp_endpoint(self, **kw):
        """Standard endpoint: token supplied via the Authorization: Bearer header."""
        return self._handle(self._bearer_token())

    @http.route('/mcp/<string:path_token>', type='http', auth='none', methods=['POST'],
                csrf=False, save_session=False)
    def mcp_endpoint_path(self, path_token, **kw):
        """Path-authenticated endpoint for clients that cannot send custom headers
        (e.g. the claude.ai web custom-connector UI). The full secret token is the
        last URL segment, so the capability URL alone grants access."""
        return self._handle(path_token)
