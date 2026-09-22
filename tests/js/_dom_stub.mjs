import { readFileSync } from 'node:fs';

/**
 * A small DOM, enough for the components whose runtime lives in the browser.
 *
 * Shared by the JavaScript harnesses so a stub defect is fixed once: two copies
 * of a fake document drift, and then one harness passes against a DOM the other
 * one cannot build. It models exactly what these components use - attributes,
 * classes, text (as text, never as markup), events, and the few selectors the
 * runtimes ask for - and nothing else on purpose.
 */

export class FakeClassList {
    constructor(node) { this.node = node; this.set = new Set(); }
    add(...names) { names.forEach((n) => this.set.add(n)); this.sync(); }
    remove(...names) { names.forEach((n) => this.set.delete(n)); this.sync(); }
    contains(name) { return this.set.has(name); }
    toggle(name, on) { if (on === undefined) on = !this.contains(name);
        if (on) this.add(name); else this.remove(name); return on; }
    sync() { this.node._class = [...this.set].join(' '); }
}

export class FakeElement {
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
    contains(node) {
        if (node === this) return true;
        return this.children.some((child) => child.contains(node));
    }
    setAttribute(name, value) { this.attributes[name] = String(value); }
    getAttribute(name) { return name in this.attributes ? this.attributes[name] : null; }
    hasAttribute(name) { return name in this.attributes; }
    removeAttribute(name) { delete this.attributes[name]; }
    addEventListener(type, handler) { (this.listeners[type] ||= []).push(handler); }
    removeEventListener(type, handler) {
        this.listeners[type] = (this.listeners[type] || []).filter((h) => h !== handler);
    }
    dispatch(type, payload = {}) {
        // Events bubble, and one component delegating from its root is the
        // whole point of a shared surface: a stub that stopped at the node it
        // was fired on would pass a harness against a runtime that never runs.
        const event = {
            target: this, currentTarget: this, preventDefault() {}, ...payload,
        };
        (this.listeners[type] || []).forEach((handler) => handler(event));
        if (this.parentNode && payload.bubbles !== false) {
            this.parentNode.dispatch(type, {...event, bubbles: true});
        }
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

export function matches(node, selector) {
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
export function elementFromTag(tag) {
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
export function treeFromHtml(html) {
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

/**
 * Install the stub as the document the runtimes will use.
 *
 * Returns the root, the fake document, and the list of elements Bootstrap was
 * asked to show - a harness asserts what the reader met, not what was called.
 */
export function installDom() {
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
    return {documentRoot, document, shown, globalThisRef};
}

/** Load a shipped runtime into the current global scope, as the shell does. */
export function loadRuntime(relative) {
    const source = readFileSync(relative, 'utf8');
    // eslint-disable-next-line no-eval
    (0, eval)(source);
}
