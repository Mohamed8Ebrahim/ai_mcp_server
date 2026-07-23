/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component, onWillUnmount } from "@odoo/owl";

// How often the pill silently re-reads the record so the live connection status
// (a time-derived computed field) updates without a manual page reload.
const MCP_REFRESH_MS = 8000;

/**
 * A small, self-contained OWL view-widget that renders the live MCP connection
 * status of the current token record as a coloured pill in the form header.
 * The value comes from the `connection_state` computed field, so the pill
 * reflects the token's REAL state (generated? revoked? expired? recently used?)
 * instead of always showing "Active".
 */
export class McpStatusPill extends Component {
    static template = "m7_mcp_ai_connector.StatusPill";
    static props = ["*"];

    setup() {
        // Periodically re-read the record so the status pill reflects live
        // connection changes (e.g. a client connecting) without a page reload.
        this._mcpTimer = setInterval(() => this._mcpRefresh(), MCP_REFRESH_MS);
        onWillUnmount(() => clearInterval(this._mcpTimer));
    }

    async _mcpRefresh() {
        const rec = this.props.record;
        if (!rec || !rec.resId) {
            return;
        }
        try {
            const dirty = typeof rec.isDirty === "function" ? await rec.isDirty() : rec.isDirty;
            if (dirty || rec.dirty) {
                return;
            }
            await rec.load();
            rec.model.notify();
        } catch {
        }
    }

    get pill() {
        const rec = this.props.record;
        const value = (rec && rec.data && rec.data.connection_state) || "draft";
        const field = rec && rec.fields && rec.fields.connection_state;
        const sel = ((field && field.selection) || []).find(([v]) => v === value);
        return {
            value,
            label: sel ? sel[1] : value,
            live: value === "active",
        };
    }
}

registry.category("view_widgets").add("mcp_status_pill", {
    component: McpStatusPill,
    fieldDependencies: [{ name: "connection_state", type: "selection" }],
});