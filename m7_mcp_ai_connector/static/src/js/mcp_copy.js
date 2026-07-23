/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component, useState, onWillUnmount } from "@odoo/owl";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

/**
 * A copy-to-clipboard field widget that works on INSECURE origins (plain HTTP),
 * where `navigator.clipboard` is unavailable. Multi-line values render as a dark
 * code block; single-line values render as an inline code chip.
 */
export class McpCopy extends Component {
    static template = "m7_mcp_ai_connector.McpCopy";
    static props = { ...standardFieldProps };

    setup() {
        this.state = useState({ copied: false });
        this._timer = null;
        onWillUnmount(() => this._timer && clearTimeout(this._timer));
    }

    get value() {
        const v = this.props.record.data[this.props.name];
        return v == null ? "" : String(v);
    }

    get isBlock() {
        return this.value.includes("\n");
    }

    async onCopy() {
        const text = this.value;
        let ok = false;
        if (window.isSecureContext && navigator.clipboard) {
            try {
                await navigator.clipboard.writeText(text);
                ok = true;
            } catch {
                ok = false;
            }
        }
        if (!ok) {
            try {
                const ta = document.createElement("textarea");
                ta.value = text;
                ta.setAttribute("readonly", "");
                ta.style.position = "fixed";
                ta.style.top = "-1000px";
                ta.style.opacity = "0";
                document.body.appendChild(ta);
                ta.focus();
                ta.select();
                ta.setSelectionRange(0, text.length);
                ok = document.execCommand("copy");
                document.body.removeChild(ta);
            } catch {
                ok = false;
            }
        }
        if (ok) {
            this.state.copied = true;
            this._timer && clearTimeout(this._timer);
            this._timer = setTimeout(() => (this.state.copied = false), 1600);
        }
    }
}

registry.category("fields").add("mcp_copy", {
    component: McpCopy,
    supportedTypes: ["char", "text"],
});