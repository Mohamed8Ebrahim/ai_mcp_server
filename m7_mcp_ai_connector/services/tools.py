import logging

from odoo import api, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# Methods that must never be reachable through odoo_call_method, even with an
# admin-scoped token, because they bypass governance or are destructive at the
# framework level.
BLOCKED_METHODS = {
    'unlink', 'browse', '_read', 'read_group', 'search', 'search_read',
    'load', 'export_data', 'check_access_rights', 'sudo', 'with_user',
    'with_context', 'with_env', '__init__', 'pool', 'env', '_cr',
    'execute_kw', 'search_fetch', 'fields_get',
}


class McpToolExecutor(models.AbstractModel):
    """Stateless service that declares and executes MCP tools.

    Every public method here runs inside ``self.env`` which the controller has
    already switched to the token owner, so Odoo's native ACLs and record rules
    apply automatically. This class only adds the MCP-specific governance layer
    (scope, model/tool allow-lists, response caps).
    """
    _name = 'mcp.tool.executor'
    _description = 'MCP Tool Executor'

    # ------------------------------------------------------------------
    # Tool catalogue exposed to the AI client (tools/list)
    # ------------------------------------------------------------------
    @api.model
    def get_tool_definitions(self, token=None):
        """Return the JSON-Schema tool definitions filtered by what is enabled
        globally and permitted for the given token."""
        registry = {t.technical_name: t for t in self.env['mcp.tool'].sudo().search([])}
        allowed_names = None
        if token and token.tool_ids:
            allowed_names = set(token.tool_ids.mapped('technical_name'))

        definitions = []
        for spec in self._all_tool_specs():
            name = spec['name']
            reg = registry.get(name)
            if reg is not None and not reg.active:
                continue
            if allowed_names is not None and name not in allowed_names:
                continue
            # A registry record, when present, may override the human description.
            if reg and reg.description:
                spec = dict(spec, description=reg.description)
            definitions.append({
                'name': spec['name'],
                'description': spec['description'],
                'inputSchema': spec['inputSchema'],
            })
        return definitions

    @api.model
    def _all_tool_specs(self):
        """Master list of built-in tools with their JSON Schemas + scope."""
        domain_schema = {
            'type': 'array',
            'description': "Odoo search domain, e.g. [[\"is_company\",\"=\",true]]. Empty means all records.",
            'items': {},
        }
        return [
            {
                'name': 'odoo_search_read', 'scope': 'read',
                'description': "Search records of a model and read selected fields in one call. "
                               "Returns a list of records as dictionaries.",
                'inputSchema': {
                    'type': 'object',
                    'properties': {
                        'model': {'type': 'string', 'description': "Technical model name, e.g. 'res.partner'."},
                        'domain': domain_schema,
                        'fields': {'type': 'array', 'items': {'type': 'string'},
                                   'description': "Field names to return. Empty returns a safe default set."},
                        'limit': {'type': 'integer', 'description': "Maximum records to return."},
                        'offset': {'type': 'integer', 'description': "Number of records to skip."},
                        'order': {'type': 'string', 'description': "Sort order, e.g. 'name asc'."},
                    },
                    'required': ['model'],
                },
            },
            {
                'name': 'odoo_read', 'scope': 'read',
                'description': "Read specific fields of records by their IDs.",
                'inputSchema': {
                    'type': 'object',
                    'properties': {
                        'model': {'type': 'string'},
                        'ids': {'type': 'array', 'items': {'type': 'integer'}},
                        'fields': {'type': 'array', 'items': {'type': 'string'}},
                    },
                    'required': ['model', 'ids'],
                },
            },
            {
                'name': 'odoo_count', 'scope': 'read',
                'description': "Count the records matching a domain without fetching them.",
                'inputSchema': {
                    'type': 'object',
                    'properties': {'model': {'type': 'string'}, 'domain': domain_schema},
                    'required': ['model'],
                },
            },
            {
                'name': 'odoo_name_search', 'scope': 'read',
                'description': "Fuzzy-search records by display name; ideal for resolving a "
                               "human name into an ID.",
                'inputSchema': {
                    'type': 'object',
                    'properties': {
                        'model': {'type': 'string'},
                        'name': {'type': 'string', 'description': "Text to search for."},
                        'limit': {'type': 'integer'},
                    },
                    'required': ['model', 'name'],
                },
            },
            {
                'name': 'odoo_read_group', 'scope': 'read',
                'description': "Aggregate records (sum/avg/count) grouped by one or more fields — "
                               "the foundation for analytics and dashboards.",
                'inputSchema': {
                    'type': 'object',
                    'properties': {
                        'model': {'type': 'string'},
                        'domain': domain_schema,
                        'fields': {'type': 'array', 'items': {'type': 'string'},
                                   'description': "Fields to aggregate, e.g. ['amount_total:sum']."},
                        'groupby': {'type': 'array', 'items': {'type': 'string'},
                                    'description': "Fields to group by, e.g. ['state']."},
                    },
                    'required': ['model', 'groupby'],
                },
            },
            {
                'name': 'odoo_fields_get', 'scope': 'read',
                'description': "Introspect a model: return each field's type, label, help and "
                               "relation. Use it before reading or writing unfamiliar models.",
                'inputSchema': {
                    'type': 'object',
                    'properties': {
                        'model': {'type': 'string'},
                        'attributes': {'type': 'array', 'items': {'type': 'string'}},
                    },
                    'required': ['model'],
                },
            },
            {
                'name': 'odoo_list_models', 'scope': 'read',
                'description': "List the available Odoo models the current user can access, "
                               "optionally filtered by a keyword.",
                'inputSchema': {
                    'type': 'object',
                    'properties': {'filter': {'type': 'string', 'description': "Optional keyword filter."}},
                },
            },
            {
                'name': 'odoo_create', 'scope': 'write',
                'description': "Create a new record. Returns the new record ID and display name.",
                'inputSchema': {
                    'type': 'object',
                    'properties': {
                        'model': {'type': 'string'},
                        'values': {'type': 'object', 'description': "Field/value mapping for the new record."},
                    },
                    'required': ['model', 'values'],
                },
            },
            {
                'name': 'odoo_write', 'scope': 'write',
                'description': "Update existing records by ID with new field values.",
                'inputSchema': {
                    'type': 'object',
                    'properties': {
                        'model': {'type': 'string'},
                        'ids': {'type': 'array', 'items': {'type': 'integer'}},
                        'values': {'type': 'object'},
                    },
                    'required': ['model', 'ids', 'values'],
                },
            },
            {
                'name': 'odoo_unlink', 'scope': 'write',
                'description': "Delete records by ID. This is irreversible — use with care.",
                'inputSchema': {
                    'type': 'object',
                    'properties': {
                        'model': {'type': 'string'},
                        'ids': {'type': 'array', 'items': {'type': 'integer'}},
                    },
                    'required': ['model', 'ids'],
                },
            },
            {
                'name': 'odoo_call_method', 'scope': 'admin',
                'description': "Execute a business method on records (e.g. action_confirm on a "
                               "sale.order). Requires an admin-scoped token.",
                'inputSchema': {
                    'type': 'object',
                    'properties': {
                        'model': {'type': 'string'},
                        'method': {'type': 'string'},
                        'ids': {'type': 'array', 'items': {'type': 'integer'}},
                        'args': {'type': 'array', 'items': {}},
                        'kwargs': {'type': 'object'},
                    },
                    'required': ['model', 'method'],
                },
            },
            # ----------------------------------------------------------------
            # OpenAI-compatible tools. ChatGPT connectors / Deep Research ONLY
            # invoke tools named exactly `search` and `fetch`, each taking a
            # single string argument and returning a JSON-stringified payload.
            # Keeping this contract lets ChatGPT read Odoo without any bridge.
            # ----------------------------------------------------------------
            {
                'name': 'search', 'scope': 'read',
                'description': "Search Odoo records by keyword across the configured business "
                               "models and return matches as {id, title, url}. This is the "
                               "entry point used by ChatGPT connectors and deep research.",
                'inputSchema': {
                    'type': 'object',
                    'properties': {
                        'query': {'type': 'string', 'description': "Free-text search query."},
                    },
                    'required': ['query'],
                },
            },
            {
                'name': 'fetch', 'scope': 'read',
                'description': "Fetch the full content of a single record previously returned by "
                               "search, identified by its 'model:id' string. Returns the record's "
                               "fields as readable text plus a link back to Odoo.",
                'inputSchema': {
                    'type': 'object',
                    'properties': {
                        'id': {'type': 'string',
                               'description': "Record identifier 'model:id' taken from a search result."},
                    },
                    'required': ['id'],
                },
            },
        ]

    @api.model
    def _spec_by_name(self, tool_name):
        for spec in self._all_tool_specs():
            if spec['name'] == tool_name:
                return spec
        return None

    # ------------------------------------------------------------------
    # Dispatch
    # ------------------------------------------------------------------
    @api.model
    def execute(self, token, tool_name, arguments):
        """Validate governance for `tool_name` then run it. Returns a JSON-able value."""
        spec = self._spec_by_name(tool_name)
        if not spec:
            raise UserError(_("Unknown tool '%s'.") % tool_name)

        reg = self.env['mcp.tool'].sudo().search(
            [('technical_name', '=', tool_name)], limit=1)
        if reg and not reg.active:
            raise UserError(_("Tool '%s' is disabled.") % tool_name)

        token._check_scope(spec['scope'])
        token._check_tool_allowed(tool_name)

        model_name = arguments.get('model')
        if model_name:
            token._check_model_allowed(model_name)

        # Map the public tool name to its handler. Native tools are prefixed
        # `odoo_`; the OpenAI-compatible `search`/`fetch` tools are not.
        handler_key = tool_name[len('odoo_'):] if tool_name.startswith('odoo_') else tool_name
        handler = getattr(self, '_tool_%s' % handler_key, None)
        if not handler:
            raise UserError(_("Tool '%s' has no implementation.") % tool_name)
        # search/fetch need the token to honour its per-model allow-list, since
        # they resolve the target model(s) themselves rather than via a `model` arg.
        if tool_name in ('search', 'fetch'):
            return handler(arguments, token)
        return handler(arguments)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _get_model(self, model_name):
        if not model_name or model_name not in self.env:
            raise UserError(_("Model '%s' does not exist.") % model_name)
        return self.env[model_name]

    def _max_records(self):
        val = self.env['ir.config_parameter'].sudo().get_param(
            'm7_mcp_ai_connector.max_records', '200')
        try:
            return max(1, int(val))
        except (TypeError, ValueError):
            return 200

    def _record_url(self, model_name, rec_id):
        """Deep link that opens the record's form view in the Odoo web client."""
        base = (self.env['ir.config_parameter'].sudo().get_param('web.base.url', '') or '').rstrip('/')
        return '%s/web#id=%s&model=%s&view_type=form' % (base, rec_id, model_name)

    def _searchable_models(self, token=None):
        """Resolve which models the ChatGPT-style `search` tool scans.

        If the token is restricted to specific models, only those are searched;
        otherwise a configurable default list is used. Every candidate is kept
        only if it exists and the acting user may read it.
        """
        if token and token.model_ids:
            names = token.model_ids.mapped('model')
        else:
            raw = self.env['ir.config_parameter'].sudo().get_param(
                'm7_mcp_ai_connector.search_models',
                'res.partner,product.template,product.product,sale.order,'
                'purchase.order,crm.lead,account.move,project.task,stock.picking')
            names = [n.strip() for n in (raw or '').split(',') if n.strip()]
        allowed = []
        for name in names:
            if name in self.env:
                model = self.env[name]
                if not model._transient and model.check_access_rights('read', raise_exception=False):
                    allowed.append(name)
        return allowed

    # ------------------------------------------------------------------
    # OpenAI-compatible tools (ChatGPT connectors / deep research)
    # ------------------------------------------------------------------
    def _tool_search(self, args, token):
        """Keyword search across the configured models. Returns the OpenAI
        connector shape: {'results': [{'id': 'model:id', 'title', 'url'}, ...]}."""
        query = (args.get('query') or '').strip()
        cap = self._max_records()
        models = self._searchable_models(token)
        results = []
        if query and models:
            per_model = max(1, cap // len(models))
            for name in models:
                model = self.env[name]
                try:
                    matches = model.name_search(name=query, limit=per_model)
                except Exception:  # noqa: BLE001 - skip models that reject name_search
                    continue
                for rec_id, display in matches:
                    results.append({
                        'id': '%s:%s' % (name, rec_id),
                        'title': display,
                        'url': self._record_url(name, rec_id),
                    })
                    if len(results) >= cap:
                        break
                if len(results) >= cap:
                    break
        return {'results': results}

    def _tool_fetch(self, args, token):
        """Return the full content of one record addressed as 'model:id',
        in the OpenAI connector shape: {'id', 'title', 'text', 'url', 'metadata'}."""
        raw = (args.get('id') or '').strip()
        model_name, sep, rec_str = raw.rpartition(':')
        if not sep or not model_name:
            raise UserError(_("Invalid id '%s'. Expected 'model:id'.") % raw)
        try:
            rec_id = int(rec_str)
        except (TypeError, ValueError):
            raise UserError(_("Invalid record id in '%s'.") % raw)
        token._check_model_allowed(model_name)
        model = self._get_model(model_name)
        record = model.browse(rec_id).exists()
        if not record:
            raise UserError(_("Record '%s' was not found.") % raw)
        values = record.read()[0]
        labels = model.fields_get(allfields=list(values.keys()), attributes=['string'])
        lines = []
        for fname, value in values.items():
            if fname == 'id' or value in (False, None, '', [], ()):
                continue
            label = labels.get(fname, {}).get('string') or fname
            lines.append('%s: %s' % (label, value))
        return {
            'id': raw,
            'title': record.display_name,
            'text': '\n'.join(lines),
            'url': self._record_url(model_name, rec_id),
            'metadata': {'model': model_name, 'record_id': rec_id},
        }

    # ------------------------------------------------------------------
    # Tool implementations
    # ------------------------------------------------------------------
    def _tool_search_read(self, args):
        model = self._get_model(args['model'])
        cap = self._max_records()
        limit = min(int(args.get('limit') or cap), cap)
        records = model.search_read(
            domain=args.get('domain') or [],
            fields=args.get('fields') or None,
            offset=int(args.get('offset') or 0),
            limit=limit,
            order=args.get('order') or None,
        )
        return {'count': len(records), 'records': records}

    def _tool_read(self, args):
        model = self._get_model(args['model'])
        records = model.browse(args['ids']).exists().read(args.get('fields') or None)
        return {'count': len(records), 'records': records}

    def _tool_count(self, args):
        model = self._get_model(args['model'])
        return {'count': model.search_count(args.get('domain') or [])}

    def _tool_name_search(self, args):
        model = self._get_model(args['model'])
        cap = self._max_records()
        limit = min(int(args.get('limit') or 20), cap)
        results = model.name_search(name=args.get('name') or '', limit=limit)
        return {'results': [{'id': r[0], 'name': r[1]} for r in results]}

    def _tool_read_group(self, args):
        model = self._get_model(args['model'])
        data = model.read_group(
            domain=args.get('domain') or [],
            fields=args.get('fields') or [],
            groupby=args.get('groupby') or [],
            lazy=False,
        )
        return {'groups': data}

    def _tool_fields_get(self, args):
        model = self._get_model(args['model'])
        attributes = args.get('attributes') or [
            'string', 'type', 'help', 'required', 'readonly', 'relation', 'selection']
        return {'fields': model.fields_get(allfields=None, attributes=attributes)}

    def _tool_list_models(self, args):
        domain = [('transient', '=', False)]
        keyword = (args.get('filter') or '').strip()
        if keyword:
            domain += ['|', ('model', 'ilike', keyword), ('name', 'ilike', keyword)]
        models_data = self.env['ir.model'].sudo().search_read(
            domain, ['model', 'name'], limit=self._max_records(), order='model')
        # Keep only models the acting user may actually read.
        allowed = []
        for m in models_data:
            if m['model'] not in self.env:
                continue
            mdl = self.env[m['model']]
            if mdl.check_access_rights('read', raise_exception=False):
                allowed.append({'model': m['model'], 'name': m['name']})
        return {'count': len(allowed), 'models': allowed}

    def _tool_create(self, args):
        model = self._get_model(args['model'])
        record = model.create(args['values'])
        return {'id': record.id, 'display_name': record.display_name}

    def _tool_write(self, args):
        model = self._get_model(args['model'])
        records = model.browse(args['ids']).exists()
        records.write(args['values'])
        return {'updated_ids': records.ids, 'count': len(records)}

    def _tool_unlink(self, args):
        model = self._get_model(args['model'])
        records = model.browse(args['ids']).exists()
        count = len(records)
        records.unlink()
        return {'deleted': count}

    def _tool_call_method(self, args):
        model = self._get_model(args['model'])
        method = args['method']
        if method.startswith('_') or method in BLOCKED_METHODS:
            raise UserError(_("Method '%s' is not allowed.") % method)
        if not hasattr(model, method):
            raise UserError(_("Model '%s' has no method '%s'.") % (args['model'], method))
        ids = args.get('ids')
        target = model.browse(ids).exists() if ids else model
        result = getattr(target, method)(*(args.get('args') or []), **(args.get('kwargs') or {}))
        # Return a JSON-safe representation.
        if isinstance(result, models.BaseModel):
            result = result.ids
        return {'result': result}
