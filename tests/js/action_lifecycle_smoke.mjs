/**
 * The action lifecycle components, exercised for real.
 *
 * The server renders the dialog and the toast region; this harness puts that
 * rendered markup in front of the real runtimes and checks what a reader would
 * actually meet: the answer the dialog gives, the words it uses, the typing
 * rule, the loading and error states, and - the one that matters most - that a
 * message can never become markup.
 *
 * Usage:
 *     node tests/js/action_lifecycle_smoke.mjs --dialog-html=/tmp/dialog.html
 */

import { readFileSync } from 'node:fs';

const args = Object.fromEntries(process.argv.slice(2).map((arg) => {
    const [key, ...rest] = arg.replace(/^--/, '').split('=');
    return [key, rest.join('=')];
}));

const failures = [];
const notes = [];
let checks = 0;

function check(what, condition, detail = '') {
    checks += 1;
    if (!condition) {
        failures.push(`${what}${detail ? ` -- ${detail}` : ''}`);
    }
}

// ---------------------------------------------------------------------------
// A small DOM, enough for these two components
// ---------------------------------------------------------------------------
class FakeClassList {
    constructor(node) { this.node = node; this.set = new Set(); }
    add(...names) { names.forEach((n) => this.set.add(n)); this.sync(); }
    remove(...names) { names.forEach((n) => this.set.delete(n)); this.sync(); }
    contains(name) { return this.set.has(name); }
    toggle(name, on) { if (on === undefined) on = !this.contains(name);
        if (on) this.add(name); else this.remove(name); return on; }
    sync() { this.node._class = [...this.set].join(' '); }
}

class FakeElement {
    constructor(tag, attrs = {}) {
        this.tagName = tag.toUpperCase();
        this.children = [];
        this.parentNode = null;
        this.attributes = {};
        this.listeners = {};
        this.style = {};
        //: Form controls have a value in a real DOM; the dialog's typed
        //: confirmation reads it, so the stub has one too.
        this._value = '';
        this._class = attrs.class || '';
        this._text = '';
        this.classList = new FakeClassList(this);
        Object.entries(attrs).forEach(([key, value]) => {
            if (key === 'class') this.classList.set = new Set(String(value).split(/\s+/).filter(Boolean));
            else this.attributes[key] = String(value);
        });
        this.classList.sync();
    }
    get value() { return this._value; }
    set value(next) { this._value = next === null || next === undefined ? '' : String(next); }
    get className() { return this._class; }
    set className(value) {
        this.classList.set = new Set(String(value).split(/\s+/).filter(Boolean));
        this.classList.sync();
    }
    get textContent() {
        return this._text + this.children.map((child) => child.textContent).join('');
    }
    set textContent(value) {
        this.children = [];
        this._text = value === null || value === undefined ? '' : String(value);
    }
    get innerHTML() { throw new Error('innerHTML is not available here'); }
    set innerHTML(_value) { throw new Error('innerHTML is not available here'); }
    get firstChild() { return this.children[0] || null; }
    appendChild(child) { child.parentNode = this; this.children.push(child); return child; }
    insertBefore(child, before) {
        child.parentNode = this;
        const index = before ? this.children.indexOf(before) : -1;
        if (index < 0) this.children.push(child); else this.children.splice(index, 0, child);
        return child;
    }
    removeChild(child) {
        const index = this.children.indexOf(child);
        if (index >= 0) this.children.splice(index, 1);
        child.parentNode = null;
        return child;
    }
    remove() { if (this.parentNode) this.parentNode.removeChild(this); }
    setAttribute(name, value) { this.attributes[name] = String(value); }
    getAttribute(name) { return name in this.attributes ? this.attributes[name] : null; }
    removeAttribute(name) { delete this.attributes[name]; }
    addEventListener(type, handler) { (this.listeners[type] ||= []).push(handler); }
    removeEventListener(type, handler) {
        this.listeners[type] = (this.listeners[type] || []).filter((h) => h !== handler);
    }
    dispatch(type, payload = {}) {
        (this.listeners[type] || []).forEach((handler) => handler({
            target: this, preventDefault() {}, ...payload,
        }));
    }
    querySelectorAll(selector) {
        const found = [];
        const walk = (node) => {
            node.children.forEach((child) => {
                if (matches(child, selector)) found.push(child);
                walk(child);
            });
        };
        walk(this);
        return found;
    }
    querySelector(selector) { return this.querySelectorAll(selector)[0] || null; }
    closest(selector) {
        let node = this;
        while (node) {
            if (matches(node, selector)) return node;
            node = node.parentNode;
        }
        return null;
    }
}

function matches(node, selector) {
    if (node.tagName !== 'DIV' || !node.classList) { /* keep going */ }
    if (selector.startsWith('.')) return node.classList.contains(selector.slice(1));
    const attribute = selector.match(/^\[([\w-]+)(?:="([^"]*)")?\]$/);
    if (attribute) {
        const value = node.getAttribute(attribute[1]);
        return attribute[2] === undefined ? value !== null : value === attribute[2];
    }
    return node.tagName === selector.toUpperCase();
}

/** Parse the attributes of a start tag into a FakeElement. */
function elementFromTag(tag) {
    const name = tag.match(/^<\s*([a-zA-Z0-9]+)/)[1];
    const attrs = {};
    const body = tag.replace(/^<\s*[a-zA-Z0-9]+/, '').replace(/\/?>$/, '');
    const pattern = /([\w:-]+)(?:="([^"]*)")?/g;
    let match;
    while ((match = pattern.exec(body))) {
        if (['/', 'aria', ''].includes(match[1])) continue;
        attrs[match[1]] = match[2] === undefined ? '' : match[2];
    }
    return new FakeElement(name, attrs);
}

/** Enough of an HTML tree for the dialog markup: elements, classes, text. */
function treeFromHtml(html) {
    const root = new FakeElement('div', { id: 'document-root' });
    const stack = [root];
    const tokens = html.split(/(<[^>]+>)/).filter((token) => token !== '');
    for (const token of tokens) {
        if (token.startsWith('<!--')) continue;
        if (token.startsWith('</')) {
            if (stack.length > 1) stack.pop();
            continue;
        }
        if (token.startsWith('<')) {
            if (/^<\s*(br|input|img|hr)\b/i.test(token) && !token.endsWith('/>')) {
                stack[stack.length - 1].appendChild(elementFromTag(token.replace(/>$/, '/>')));
                continue;
            }
            const node = elementFromTag(token);
            stack[stack.length - 1].appendChild(node);
            if (!/\/>$/.test(token)) stack.push(node);
            continue;
        }
        // Text is appended, never assigned: the setter clears children, and
        // clearing them here is how a parsed tree silently becomes one node.
        stack[stack.length - 1]._text += token.replace(/\s+/g, ' ');
    }
    return root;
}

const documentRoot = new FakeElement('div', {});
const document = {
    createElement: (tag) => new FakeElement(tag),
    querySelector: (selector) => documentRoot.querySelector(selector),
    querySelectorAll: (selector) => documentRoot.querySelectorAll(selector),
    getElementById: (id) => documentRoot.querySelector(`[id="${id}"]`),
};

const shown = [];
const globalThisRef = globalThis;
globalThisRef.document = document;
globalThisRef.window = globalThisRef;
globalThisRef.bootstrap = {
    Modal: class {
        constructor(node) { this.node = node; }
        static getOrCreateInstance(node) { return new this(node); }
        show() { shown.push(this.node); }
        hide() { this.node.dispatch('hidden.bs.modal'); }
    },
    Toast: class {
        constructor(node) { this.node = node; }
        static getOrCreateInstance(node) { return new this(node); }
        show() { shown.push(this.node); }
    },
};
globalThisRef.setTimeout = setTimeout;
globalThisRef.console = console;
globalThisRef.confirm = () => { throw new Error('the browser dialog must not be used'); };

// ---------------------------------------------------------------------------
// The real runtimes, and the server's own rendered dialog
// ---------------------------------------------------------------------------
for (const file of ['static/js/modules/core/confirm-dialog.js',
                    'static/js/modules/core/toast.js']) {
    const source = readFileSync(file, 'utf8');
    // eslint-disable-next-line no-eval
    (0, eval)(source);
}
check('the dialog runtime is defined', typeof globalThisRef.ConfirmDialog === 'object');
check('the toast runtime is defined', typeof globalThisRef.Toast === 'object');

const dialogHtml = readFileSync(args['dialog-html'], 'utf8');
documentRoot.appendChild(treeFromHtml(dialogHtml));

const dialog = documentRoot.querySelector('[data-confirm-dialog]');
check('the server rendered a dialog component', dialog !== null);
check('the dialog declares the action it is asking about',
      dialog.getAttribute('data-confirm-action') === 'files.delete_selected',
      dialog.getAttribute('data-confirm-action'));
check('the dialog is a modal dialog with a name and a description',
      dialog.getAttribute('role') === 'dialog'
      && dialog.getAttribute('aria-modal') === 'true'
      && dialog.getAttribute('aria-labelledby') !== null
      && dialog.getAttribute('aria-describedby') !== null);
check('the dialog carries the Action Registry confirmation key',
      dialog.getAttribute('data-confirm-key') === 'action.files.delete_selected.confirm');

// ---------------------------------------------------------------------------
// Asking
// ---------------------------------------------------------------------------
async function answer(how, spec) {
    const promise = globalThisRef.ConfirmDialog.request(spec);
    if (how === 'accept') {
        dialog.querySelector('[data-confirm-accept]')
            .closest('[data-confirm-dialog]') ?? null;
        dialog.dispatch('click', {target: dialog.querySelector('[data-confirm-accept]')});
    } else if (how === 'cancel') {
        dialog.dispatch('click', {target: dialog.querySelector('[data-confirm-cancel]')});
    } else {
        dialog.dispatch('hidden.bs.modal');
    }
    return promise;
}

const accepted = await answer('accept', {
    action: 'files.delete_selected',
    title: 'Delete 27 files?',
    message: 'This permanently removes the selected records.',
    scope: '27 files',
    confirmLabel: 'Delete 27 Files',
    cancelLabel: 'Keep them',
    dangerous: true,
});
check('accepting returns true', accepted === true);
check('the scope the page passed is shown',
      dialog.querySelector('[data-confirm-scope]').textContent.includes('27 files'));
check('the accepting button carries the page wording',
      dialog.querySelector('[data-confirm-accept]').textContent.includes('Delete 27 Files'));
check('the cancelling button carries the page wording',
      dialog.querySelector('[data-confirm-cancel]').textContent.includes('Keep them'));
check('a dangerous action is drawn as one',
      dialog.getAttribute('data-confirm-dangerous') === 'true'
      && dialog.querySelector('[data-confirm-accept]').classList.contains('btn-danger'));

const refused = await answer('cancel', {action: 'files.delete_selected'});
check('cancelling returns false', refused === false);
const dismissed = await answer('dismiss', {action: 'files.delete_selected'});
check('dismissing the dialog is not consent', dismissed === false);

// Loading and error are states of the answer, not new dialogs.
globalThisRef.ConfirmDialog.setLoading(dialog, true);
check('loading disables the accepting button',
      dialog.querySelector('[data-confirm-accept]').getAttribute('aria-disabled') === 'true');
globalThisRef.ConfirmDialog.setLoading(dialog, false);
globalThisRef.ConfirmDialog.setError(dialog, 'The export failed.');
check('an error is shown in the dialog, not in the console',
      dialog.querySelector('[data-confirm-error]').textContent.includes('The export failed.'));
globalThisRef.ConfirmDialog.setError(dialog, '');

// The typed-confirmation rule. The question stays open while it is checked,
// and is dismissed at the end - dismissing is never consent.
const typed = globalThisRef.ConfirmDialog.request({
    action: 'files.delete_selected', typed: 'DELETE', dangerous: true,
});
const acceptButton = dialog.querySelector('[data-confirm-accept]');
const field = dialog.querySelector('[data-confirm-typed-input]');
check('a typed confirmation starts locked', acceptButton.disabled === true);
field.value = 'delete';
if (field.oninput) field.oninput();
check('the wrong word keeps it locked', acceptButton.disabled === true);
field.value = 'DELETE';
if (field.oninput) field.oninput();
check('the right word unlocks it', acceptButton.disabled === false);
dialog.dispatch('hidden.bs.modal');
check('an unanswered typed confirmation resolves as a refusal',
      (await typed) === false);

// A page with no dialog must not invent one.
const orphan = documentRoot.querySelector('[data-confirm-dialog]');
orphan.remove();
const noDialog = await globalThisRef.ConfirmDialog.request({action: 'x.y'});
check('without the component the answer is a refusal, not a browser dialog',
      noDialog === false);
documentRoot.appendChild(treeFromHtml(dialogHtml));

// ---------------------------------------------------------------------------
// Telling the reader what happened
// ---------------------------------------------------------------------------
const region = documentRoot.appendChild(new FakeElement('div', {'data-toast-region': ''}));
globalThisRef.Toast.success('27 files categorised.');
const success = region.querySelector('[data-toast]');
check('a success toast appears in the shared region', success !== null);
check('a success is announced politely',
      success.getAttribute('role') === 'status'
      && success.getAttribute('aria-live') === 'polite');
check('a success says what happened',
      success.textContent.includes('27 files categorised.'));

globalThisRef.Toast.error('Export failed.', {correlationId: 'ERR-20260921-0042'});
const failure = region.querySelectorAll('[data-toast]').pop();
check('a failure is announced assertively', failure.getAttribute('role') === 'alert');
check('a failure carries the correlation id and nothing technical',
      failure.textContent.includes('ERR-20260921-0042')
      && !/Traceback|psycopg2|SELECT |C:\\\\/.test(failure.textContent));

const before = region.querySelectorAll('[data-toast]').length;
globalThisRef.Toast.info('<b>not markup</b>');
const message = region.querySelectorAll('[data-toast-message]').pop();
check('a message is text, never markup',
      message.textContent === '<b>not markup</b>'
      && message.children.length === 0);
notes.push(`toasts in the region: ${before + 1}`);

// ---------------------------------------------------------------------------
// Report
// ---------------------------------------------------------------------------
for (const note of notes) {
    console.log(`note: ${note}`);
}
if (failures.length) {
    failures.forEach((failure) => console.log(`FAIL ${failure}`));
    console.log(`${checks - failures.length}/${checks} checks passed`);
    process.exit(1);
}
console.log(`${checks}/${checks} checks passed`);
