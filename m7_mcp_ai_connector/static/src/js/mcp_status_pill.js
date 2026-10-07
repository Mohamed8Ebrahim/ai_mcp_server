odoo.define('m7_mcp_ai_connector.mcp_status_pill', function (require) {
"use strict";

var widgetRegistry = require('web.widget_registry');
var Widget = require('web.Widget');
var core = require('web.core');
var qweb = core.qweb;

var McpStatusPill = Widget.extend({
    template: 'm7_mcp_ai_connector.StatusPill',

    init: function (parent, record, node) {
        this._super.apply(this, arguments);
        this.record = record;
        this.node = node;
        this.pill = this._getPillData();
    },

    _getPillData: function () {
        var recData = (this.record && this.record.data) || {};
        var value = recData.connection_state || 'draft';
        var field = this.record && this.record.fields && this.record.fields.connection_state;
        var selection = (field && field.selection) || [];
        var label = value;
        for (var i = 0; i < selection.length; i++) {
            if (selection[i][0] === value) {
                label = selection[i][1];
                break;
            }
        }
        return {
            value: value,
            label: label,
            live: value === 'active',
        };
    },
});

widgetRegistry.add('mcp_status_pill', McpStatusPill);

return McpStatusPill;
});
