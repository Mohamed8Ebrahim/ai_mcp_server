import json
import time
import logging

from odoo import api, models, _
from odoo.exceptions import UserError, AccessError

_logger = logging.getLogger(__name__)

PROTOCOL_VERSION = '2024-11-05'
SERVER_NAME = 'Odoo MCP Server'
SERVER_VERSION = '17.0.1.0.0'

# JSON-RPC 2.0 standard error codes.
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603


class McpProtocol(models.AbstractModel):
    """Implements the MCP JSON-RPC 2.0 message layer over Streamable HTTP."""
    _name = 'mcp.protocol'
    _description = 'MCP Protocol Handler'

    @api.model
    def handle_message(self, message, token, client_ip=None):
        """Process a single JSON-RPC message.

        Returns a JSON-RPC response dict, or ``None`` for notifications
        (messages without an ``id``) which must not be answered.
        """
        if not isinstance(message, dict):
            return self._error(None, INVALID_REQUEST, "Invalid JSON-RPC message.")

        msg_id = message.get('id')
        method = message.get('method')
        params = message.get('params') or {}
        is_notification = 'id' not in message

        if not method:
            return None if is_notification else self._error(msg_id, INVALID_REQUEST, "Missing method.")

        try:
            if method == 'initialize':
                result = self._on_initialize(params)
            elif method in ('notifications/initialized', 'notifications/cancelled'):
                return None
            elif method == 'ping':
                result = {}
            elif method == 'tools/list':
                result = self._on_tools_list(token)
            elif method == 'tools/call':
                result = self._on_tools_call(params, token, client_ip)
            elif method in ('resources/list', 'prompts/list'):
                # Declared-but-empty so clients that probe them don't error out.
                result = {'resources': []} if method.startswith('resources') else {'prompts': []}
            else:
                if is_notification:
                    return None
                return self._error(msg_id, METHOD_NOT_FOUND, _("Unknown method '%s'.") % method)
        except UserError as e:
            return None if is_notification else self._error(msg_id, INVALID_PARAMS, str(e))
        except AccessError as e:
            return None if is_notification else self._error(msg_id, INVALID_PARAMS, _("Access denied: %s") % str(e))
        except Exception as e:  # noqa: BLE001 - surface everything cleanly to the client
            _logger.exception("MCP internal error on method %s", method)
            return None if is_notification else self._error(msg_id, INTERNAL_ERROR, str(e))

        # Connection-level activity (handshake / listing / keep-alive) marks the
        # token as live so the Connection Status flips to "Connected" as soon as
        # a client connects — tool calls already register via _register_use.
        if method in ('initialize', 'tools/list', 'ping'):
            try:
                token._touch(client_ip)
            except Exception:  # noqa: BLE001 - never break the response over a touch
                _logger.exception("MCP: failed to touch token on %s", method)

        return None if is_notification else {'jsonrpc': '2.0', 'id': msg_id, 'result': result}

    # ------------------------------------------------------------------
    # Method handlers
    # ------------------------------------------------------------------
    def _on_initialize(self, params):
        client_version = params.get('protocolVersion') or PROTOCOL_VERSION
        return {
            'protocolVersion': client_version,
            'capabilities': {
                'tools': {'listChanged': False},
                'logging': {},
            },
            'serverInfo': {'name': SERVER_NAME, 'version': SERVER_VERSION},
            'instructions': (
                "This server exposes an Odoo ERP database. Use odoo_list_models and "
                "odoo_fields_get to discover schema, odoo_search_read / odoo_read_group "
                "to query and analyze, and the write tools only when explicitly asked. "
                "All actions are audited and constrained by the access token's scope."
            ),
        }

    def _on_tools_list(self, token):
        executor = self.env['mcp.tool.executor']
        return {'tools': executor.get_tool_definitions(token=token)}

    def _on_tools_call(self, params, token, client_ip):
        tool_name = params.get('name')
        arguments = params.get('arguments') or {}
        if not tool_name:
            raise UserError(_("Missing tool name."))

        started = time.time()
        log_vals = {
            'token_id': token.id,
            'user_id': self.env.uid,
            'method': 'tools/call',
            'tool_name': tool_name,
            'model_name': arguments.get('model'),
            'arguments': json.dumps(arguments, default=str)[:8000],
            'client_ip': client_ip,
        }
        try:
            executor = self.env['mcp.tool.executor']
            data = executor.execute(token, tool_name, arguments)
            duration = (time.time() - started) * 1000.0
            self._write_log(dict(log_vals, success=True, duration_ms=duration,
                                 result_summary=self._summarize(data)))
            token._register_use(client_ip)
            return {
                'content': [{'type': 'text', 'text': json.dumps(data, default=str, ensure_ascii=False)}],
                'isError': False,
            }
        except Exception as e:  # noqa: BLE001
            duration = (time.time() - started) * 1000.0
            self._write_log(dict(log_vals, success=False, duration_ms=duration,
                                 error_message=str(e)))
            # MCP convention: tool errors are reported inside a successful JSON-RPC
            # response with isError=true, so the model can read and react to them.
            return {
                'content': [{'type': 'text', 'text': _("Error: %s") % str(e)}],
                'isError': True,
            }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _write_log(self, vals):
        """Persist an audit entry in a separate transaction-safe way."""
        try:
            self.env['mcp.log'].sudo().create(vals)
        except Exception:  # noqa: BLE001 - logging must never break the response
            _logger.exception("Failed to write MCP audit log")

    @staticmethod
    def _summarize(data):
        if isinstance(data, dict):
            for key in ('count', 'deleted', 'id'):
                if key in data:
                    return '%s=%s' % (key, data[key])
            if 'updated_ids' in data:
                return 'updated=%s' % len(data['updated_ids'])
            if 'records' in data:
                return 'records=%s' % len(data['records'])
        return 'ok'

    @staticmethod
    def _error(msg_id, code, message):
        return {'jsonrpc': '2.0', 'id': msg_id, 'error': {'code': code, 'message': message}}
