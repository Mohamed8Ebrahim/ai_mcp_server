odoo.define('m7_mcp_ai_connector.mcp_copy', function (require) {
"use strict";

var AbstractField = require('web.AbstractField');
var field_registry = require('web.field_registry');
var core = require('web.core');
var qweb = core.qweb;
var _t = core._t;

var McpCopy = AbstractField.extend({
    events: _.extend({}, AbstractField.prototype.events, {
        'click .o_mcp_copy_btn': '_onCopyClick',
    }),

    _renderReadonly: function () {
        var value = this.value || '';
        var isBlock = typeof value === 'string' && value.indexOf('\n') !== -1;
        this.$el.empty().append(qweb.render('m7_mcp_ai_connector.McpCopy', {
            value: value,
            isBlock: isBlock,
            isEmpty: !value,
        }));
    },

    _renderEdit: function () {
        this._renderReadonly();
    },

    _onCopyClick: function (ev) {
        ev.preventDefault();
        ev.stopPropagation();
        var self = this;
        var text = this.value || '';
        var $btn = this.$('.o_mcp_copy_btn');

        var markCopied = function () {
            $btn.find('i').removeClass('fa-clipboard').addClass('fa-check');
            $btn.find('span').text(_t('Copied!'));
            setTimeout(function () {
                $btn.find('i').removeClass('fa-check').addClass('fa-clipboard');
                $btn.find('span').text(_t('Copy'));
            }, 1600);
        };

        if (window.isSecureContext && navigator.clipboard) {
            navigator.clipboard.writeText(text).then(markCopied, function () {
                self._fallbackCopy(text, markCopied);
            });
        } else {
            this._fallbackCopy(text, markCopied);
        }
    },

    _fallbackCopy: function (text, onSuccess) {
        try {
            var ta = document.createElement('textarea');
            ta.value = text;
            ta.setAttribute('readonly', '');
            ta.style.position = 'fixed';
            ta.style.top = '-1000px';
            ta.style.opacity = '0';
            document.body.appendChild(ta);
            ta.focus();
            ta.select();
            ta.setSelectionRange(0, text.length);
            var ok = document.execCommand('copy');
            document.body.removeChild(ta);
            if (ok && onSuccess) {
                onSuccess();
            }
        } catch (e) {
            console.error('Copy failed', e);
        }
    },
});

field_registry.add('mcp_copy', McpCopy);

return McpCopy;
});
