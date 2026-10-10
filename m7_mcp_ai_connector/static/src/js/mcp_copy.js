/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component, useState, onWillUnmount, useRef } from "@odoo/owl";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

/**
 * Copy-to-clipboard field widget.
 * Works on insecure HTTP origins and inside Bootstrap/OWL dialogs by appending
 * the fallback textarea inside the widget root (not document.body).
 */
export class McpCopy extends Component {
    setup() {
        this.state = useState({ copied: false });
        this.rootRef = useRef("root");
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

    get isEmpty() {
        return !this.value;
    }

    async onCopy() {
        const text = this.value;
        if (!text) {
            return;
        }
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
            ok = this._fallbackCopy(text);
        }
        if (ok) {
            this.state.copied = true;
            this._timer && clearTimeout(this._timer);
            this._timer = setTimeout(() => (this.state.copied = false), 1600);
        } else {
            window.prompt("Press Ctrl+C to copy", text);
        }
    }

    _fallbackCopy(text) {
        // Must stay inside the dialog/modal — body append fails when focus is trapped.
        const container = this.rootRef.el || this.el || document.body;
        const ta = document.createElement("textarea");
        ta.value = text;
        ta.setAttribute("readonly", "");
        ta.style.cssText =
            "position:fixed;top:0;left:0;width:1px;height:1px;padding:0;border:0;outline:none;box-shadow:none;background:transparent;";
        container.appendChild(ta);
        ta.focus();
        ta.select();
        ta.setSelectionRange(0, text.length);
        let ok = false;
        try {
            ok = document.execCommand("copy");
        } catch {
            ok = false;
        }
        container.removeChild(ta);
        return ok;
    }
}
McpCopy.template = "m7_mcp_ai_connector.McpCopy";
McpCopy.props = { ...standardFieldProps };

registry.category("fields").add("mcp_copy", {
    component: McpCopy,
    supportedTypes: ["char", "text"],
});
