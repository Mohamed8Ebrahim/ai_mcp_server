odoo.define('m7_mcp_ai_connector.mcp_copy', function (require) {
"use strict";

/**
 * Copy-to-clipboard field widget for Odoo 13.
 *
 * Uses ClipboardJS with `container: this.$el[0]` — required inside Bootstrap
 * modals (token reveal wizard). Appending a textarea to document.body and
 * calling execCommand('copy') fails there because the modal steals focus.
 * See: https://github.com/zenorocha/clipboard.js/issues/155
 * (same approach as web's built-in CopyClipboardChar).
 */

var AbstractField = require('web.AbstractField');
var field_registry = require('web.field_registry');
var core = require('web.core');
var qweb = core.qweb;
var _t = core._t;

var McpCopy = AbstractField.extend({
    className: 'o_field_mcp_copy',
    supportedFieldTypes: ['char', 'text'],

    destroy: function () {
        this._destroyClipboard();
        this._super.apply(this, arguments);
    },

    _destroyClipboard: function () {
        if (this.clipboard) {
            this.clipboard.destroy();
            this.clipboard = null;
        }
    },

    _renderReadonly: function () {
        var value = this.value || '';
        var isBlock = typeof value === 'string' && value.indexOf('\n') !== -1;
        this._destroyClipboard();
        this.$el.empty().append(qweb.render('m7_mcp_ai_connector.McpCopy', {
            value: value,
            isBlock: isBlock,
            isEmpty: !value,
        }));
        if (value) {
            this._initClipboard();
        }
    },

    _renderEdit: function () {
        // Always show the copy UI (wizard fields are readonly but open in "edit").
        this._renderReadonly();
    },

    _initClipboard: function () {
        var self = this;
        var $btn = this.$('.o_mcp_copy_btn');
        if (!$btn.length || typeof ClipboardJS === 'undefined') {
            // Fallback if ClipboardJS is unavailable for any reason.
            $btn.off('click.mcp_copy').on('click.mcp_copy', function (ev) {
                ev.preventDefault();
                ev.stopPropagation();
                self._fallbackCopy(self.value || '', function () {
                    self._markCopied($btn);
                });
            });
            return;
        }
        this.clipboard = new ClipboardJS($btn[0], {
            text: function () {
                return self.value || '';
            },
            // Keep selection inside the modal so Bootstrap cannot steal focus.
            container: self.$el[0],
        });
        this.clipboard.on('success', function () {
            self._markCopied($btn);
        });
        this.clipboard.on('error', function () {
            self._fallbackCopy(self.value || '', function () {
                self._markCopied($btn);
            });
        });
    },

    _markCopied: function ($btn) {
        $btn.find('i').removeClass('fa-clipboard').addClass('fa-check');
        $btn.find('span').text(_t('Copied!'));
        setTimeout(function () {
            $btn.find('i').removeClass('fa-check').addClass('fa-clipboard');
            $btn.find('span').text(_t('Copy'));
        }, 1600);
    },

    _fallbackCopy: function (text, onSuccess) {
        // Append inside this widget (inside the modal), never document.body.
        var container = (this.$el && this.$el[0]) || document.body;
        var ta = document.createElement('textarea');
        ta.value = text;
        ta.setAttribute('readonly', '');
        ta.style.cssText = 'position:fixed;top:0;left:0;width:1px;height:1px;padding:0;border:0;outline:none;box-shadow:none;background:transparent;';
        container.appendChild(ta);
        ta.focus();
        ta.select();
        ta.setSelectionRange(0, text.length);
        var ok = false;
        try {
            ok = document.execCommand('copy');
        } catch (e) {
            ok = false;
        }
        container.removeChild(ta);
        if (ok) {
            if (onSuccess) {
                onSuccess();
            }
        } else {
            window.prompt(_t('Press Ctrl+C to copy'), text);
        }
    },
});

field_registry.add('mcp_copy', McpCopy);

return McpCopy;
});
