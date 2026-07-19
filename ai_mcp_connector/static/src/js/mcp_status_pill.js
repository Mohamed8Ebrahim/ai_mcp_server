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
    setup() {
        // Periodically re-read the record so the status pill reflects live
        // connection changes (e.g. a client connecting) without a page reload.
        this._mcpTimer = setInterval(() => this._mcpRefresh(), MCP_REFRESH_MS);
        onWillUnmount(() => clearInterval(this._mcpTimer));
    }

    async _mcpRefresh() {
        const rec = this.props.record;
        if (!rec || !rec.resId) {
            return; // unsaved / new record: nothing to reload
        }
        try {
            // Never discard the user's unsaved edits.
            if (await rec.isDirty()) {
                return;
            }
            await rec.model.load();
        } catch {
            // Ignore transient reload errors (offline, concurrent save, ...).
        }
    }

    get pill() {
        const rec = this.props.record;
        const value = (rec && rec.data && rec.data.connection_state) || "draft";
        // Selection labels are translated by Odoo, so reuse them as the pill text.
        const field = rec && rec.fields && rec.fields.connection_state;
        const sel = (field && field.selection || []).find(([v]) => v === value);
        return {
            value,
            label: sel ? sel[1] : value,
            // A dot only pulses for a genuinely live connection.
            live: value === "active",
        };
    }
}
McpStatusPill.template = "ai_mcp_connector.StatusPill";
McpStatusPill.props = ["*"];

registry.category("view_widgets").add("mcp_status_pill", {
    component: McpStatusPill,
    fieldDependencies: [{ name: "connection_state", type: "selection" }],
});
