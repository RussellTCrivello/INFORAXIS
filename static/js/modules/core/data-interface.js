/**
 * INFORAXIS Data Interface System
 *
 * Progressive enhancement for every structured table and Add/Create modal.
 * The module is intentionally framework-free so legacy Jinja templates and
 * dynamically-rendered rows inherit the same interaction model without
 * replacing existing API calls or business logic.
 */

const TABLE_ENHANCED = 'iaEnhanced';
const MODAL_ENHANCED = 'iaModalEnhanced';
const FORM_ENHANCED = 'iaFormEnhanced';
const SORT_STATE = new WeakMap();
const TABLE_OBSERVERS = new WeakMap();

const SELECTOR = {
    tables: 'table',
    modals: '.modal',
    focusable: [
        'input:not([type="hidden"]):not([disabled]):not([readonly])',
        'select:not([disabled])',
        'textarea:not([disabled]):not([readonly])',
        'button:not([disabled])',
        'a[href]',
        '[tabindex]:not([tabindex="-1"])'
    ].join(',')
};

const EMPTY_VALUES = new Set(['', '-', '—', 'n/a', 'na', 'none', 'null', 'undefined', 'unknown']);

function safeLocalStorage() {
    try {
        if (window.localStorage) return window.localStorage;
    } catch (error) {
        // ignored: private browsing / security policies
    }
    return null;
}

function textOf(node) {
    return (node?.textContent || '').replace(/\s+/g, ' ').trim();
}

function normalizeLabel(label) {
    return String(label || '').replace(/[:#]/g, ' ').replace(/\s+/g, ' ').trim().toLowerCase();
}

function escapeHtml(value) {
    const div = document.createElement('div');
    div.textContent = value == null ? '' : String(value);
    return div.innerHTML;
}

function escapeAttr(value) {
    return escapeHtml(value).replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

function closestTableWrapper(table) {
    return table.closest('.ia-table-scroll, .table-wrapper, .table-responsive');
}

function shouldEnhanceTable(table) {
    if (!(table instanceof HTMLTableElement)) return false;
    if (table.dataset.iaEnhance === 'false' || table.closest('[data-ia-skip="true"]')) return false;
    if (table.closest('.tox, .select2-container, .flatpickr-calendar')) return false;

    const hasHeader = !!(table.tHead && table.tHead.rows.length);
    const looksTabular = table.classList.contains('files-table') || table.classList.contains('data-table') || table.classList.contains('custom-table') || table.classList.contains('table');
    return hasHeader && looksTabular;
}

function ensureTableWrapper(table) {
    const existing = closestTableWrapper(table);
    if (existing) {
        existing.classList.add('ia-table-scroll');
        if (!existing.getAttribute('role')) existing.setAttribute('role', 'region');
        if (!existing.getAttribute('aria-label')) {
            const heading = existing.closest('.section-card, .stat-card, .card')?.querySelector('h1,h2,h3,h4,h5,h6');
            if (heading) existing.setAttribute('aria-label', textOf(heading));
        }
        return existing;
    }

    const wrapper = document.createElement('div');
    wrapper.className = 'ia-table-scroll';
    wrapper.setAttribute('role', 'region');
    wrapper.setAttribute('aria-label', table.getAttribute('aria-label') || table.caption?.textContent?.trim() || 'Data table');
    table.parentNode.insertBefore(wrapper, table);
    wrapper.appendChild(table);
    return wrapper;
}

function inferColumnType(label, index, th) {
    const normalized = normalizeLabel(label);
    const hasCheckbox = !!th.querySelector('input[type="checkbox"]');
    if (hasCheckbox || /^select/.test(normalized)) return 'select';
    if (/action|operation|controls?|tools?|manage/.test(normalized)) return 'actions';
    if (/^id$|\bid\b|identifier|uuid|hash id|^#$|number/.test(normalized)) return index <= 1 ? 'id' : 'number';
    if (/size|bytes|kb|mb|gb|storage/.test(normalized)) return 'size';
    if (/count|usage|frequency|files?|words?|documents?|sources?|categories?|total|records?|items?/.test(normalized)) return 'count';
    if (/progress|percent|rate|success rate/.test(normalized)) return 'progress';
    if (/date|time|created|updated|started|completed|timestamp|assigned at/.test(normalized)) return 'date';
    if (/duration|elapsed/.test(normalized)) return 'duration';
    if (/status|state|validation|active|enabled/.test(normalized)) return 'status';
    if (/path|folder|directory|location|hash$|checksum/.test(normalized)) return 'path';
    if (/type|role|source|side|category|keyword|domain|method|capability|priority|user|analyst/.test(normalized)) return 'tag';
    return 'text';
}

function tableHeaderCells(table) {
    const rows = table.tHead ? Array.from(table.tHead.rows) : [];
    return rows.length ? Array.from(rows[rows.length - 1].cells) : [];
}

function applyColumnSemantics(table) {
    const headers = tableHeaderCells(table);
    if (!headers.length) return;

    headers.forEach((th, index) => {
        const type = th.dataset.iaType || inferColumnType(textOf(th), index, th);
        th.dataset.iaType = type;
        if (type === 'actions') th.classList.add('ia-cell-actions');
        if (type === 'select') th.classList.add('ia-cell-select');
        if (['number', 'count', 'size', 'progress'].includes(type)) th.classList.add('ia-cell-number');
    });

    Array.from(table.tBodies).forEach((tbody) => {
        Array.from(tbody.rows).forEach((row) => decorateRow(row, headers));
    });
}

function decorateRow(row, headers) {
    if (row.cells.length === 1 && row.cells[0].hasAttribute('colspan')) {
        const value = textOf(row.cells[0]).toLowerCase();
        row.classList.toggle('ia-table-loading-row', /loading|processing/.test(value));
        row.classList.toggle('ia-table-error-row', /error|failed|invalid/.test(value));
        row.classList.toggle('ia-table-empty-row', !/loading|processing|error|failed|invalid/.test(value));
        return;
    }

    const rowText = textOf(row).toLowerCase();
    if (/failed|error|invalid|denied|blocked/.test(rowText)) row.classList.add('is-problem');

    Array.from(row.cells).forEach((cell, index) => {
        const type = headers[index]?.dataset.iaType || inferColumnType(textOf(headers[index]), index, headers[index] || cell);
        cell.dataset.iaType = cell.dataset.iaType || type;
        decorateCell(cell, type, index);
    });
}

function decorateCell(cell, type, index) {
    if (type === 'actions') {
        cell.classList.add('ia-cell-actions');
        const group = cell.querySelector('.btn-group, .action-buttons');
        if (group) group.classList.add('ia-action-group');
    }
    if (type === 'select') cell.classList.add('ia-cell-select');
    if (['number', 'count', 'size', 'progress'].includes(type)) cell.classList.add('ia-cell-number');
    if (['date', 'time', 'duration'].includes(type)) cell.classList.add('ia-cell-date');
    if (type === 'id') cell.classList.add('ia-cell-id');
    if (type === 'path') decoratePathCell(cell);
    if (type === 'status' || type === 'tag') decorateStatusOrTagCell(cell, type);

    if (index > 0 && type === 'text' && !cell.classList.contains('ia-cell-primary') && isLikelyPrimaryText(cell)) {
        cell.classList.add('ia-cell-primary');
        cell.dataset.iaRole = 'primary';
    }

    normalizeEmptyCell(cell);
    addTitleForTruncatedContent(cell, type);
}

function isLikelyPrimaryText(cell) {
    const value = textOf(cell);
    if (!value || value.length < 2) return false;
    if (cell.querySelector('button, input, select, textarea')) return false;
    return !!cell.querySelector('strong, a') || value.length > 18;
}

function decoratePathCell(cell) {
    cell.classList.add('ia-cell-path');
    cell.setAttribute('dir', 'ltr');
    const value = textOf(cell);
    if (!value || cell.querySelector('.ia-path-value')) return;
    if (cell.childElementCount === 0 || (cell.childElementCount === 1 && cell.firstElementChild?.tagName === 'SPAN')) {
        const content = cell.innerHTML.trim() || escapeHtml(value);
        cell.innerHTML = `<span class="ia-path-value" title="${escapeAttr(value)}">${content}</span>`;
    }
}

function decorateStatusOrTagCell(cell, type) {
    const badges = cell.querySelectorAll('.badge');
    if (badges.length) {
        badges.forEach((badge) => normalizeBadgeTone(badge));
        return;
    }

    const value = textOf(cell);
    if (!value || EMPTY_VALUES.has(value.toLowerCase())) return;
    if (cell.querySelector('select, input, button, a')) return;

    const tone = statusTone(value, type);
    cell.innerHTML = `<span class="ia-status-badge" data-ia-tone="${tone}">${escapeHtml(value)}</span>`;
}

function normalizeBadgeTone(badge) {
    if (badge.dataset.iaTone) return;
    const value = textOf(badge);
    const classes = Array.from(badge.classList).join(' ');
    let tone = statusTone(value, 'status');
    if (/bg-success|badge-success|text-success/.test(classes)) tone = 'success';
    if (/bg-warning|badge-warning|text-warning/.test(classes)) tone = 'warning';
    if (/bg-danger|badge-danger|text-danger/.test(classes)) tone = 'danger';
    if (/bg-info|badge-info|text-info/.test(classes)) tone = 'info';
    if (/bg-secondary|badge-secondary|text-muted/.test(classes)) tone = 'neutral';
    badge.dataset.iaTone = tone;
    badge.classList.add('ia-status-badge');
}

function statusTone(value, fallbackType = 'status') {
    const v = normalizeLabel(value);
    if (/success|complete|completed|done|read|active|enabled|valid|ok|yes|allowed|open|public|resolved|analyzed/.test(v)) return 'success';
    if (/pending|queued|processing|running|warning|temp|temporary|unread|limited|restricted|wait|scheduled|draft/.test(v)) return 'warning';
    if (/failed|error|invalid|inactive|disabled|denied|blocked|deleted|no|none|confidential|classified/.test(v)) return 'danger';
    if (/info|new|created|updated|analyst|category|source|side|keyword|viewer|admin/.test(v) || fallbackType === 'tag') return 'info';
    return 'neutral';
}

function normalizeEmptyCell(cell) {
    if (cell.children.length > 0) return;
    const raw = textOf(cell);
    if (!EMPTY_VALUES.has(raw.toLowerCase())) return;
    cell.innerHTML = '<span class="ia-empty-value" title="No value">—</span>';
}

function addTitleForTruncatedContent(cell, type) {
    if (cell.querySelector('input, select, textarea, button')) return;
    const value = textOf(cell);
    if (!value || value.length < 28) return;
    if (!cell.getAttribute('title')) cell.setAttribute('title', value);
    if (['text', 'tag'].includes(type) && cell.childElementCount === 0) {
        cell.innerHTML = `<span class="ia-truncate">${escapeHtml(value)}</span>`;
    }
}

function hasSortableRows(table) {
    const tbody = table.tBodies[0];
    if (!tbody) return false;
    const rows = Array.from(tbody.rows).filter((row) => row.cells.length > 1 && !row.cells[0]?.hasAttribute('colspan'));
    return rows.length > 1;
}

function isHeaderSortable(th, table) {
    const type = th.dataset.iaType;
    if (table.dataset.iaSort === 'false' || table.dataset.iaServerSort === 'true') return false;
    if (['select', 'actions'].includes(type)) return false;
    if (th.querySelector('button, input, select, textarea, a')) return false;
    return hasSortableRows(table);
}

function setupTableSorting(table) {
    if (table.dataset.iaSortingSetup === 'true') return;
    const headers = tableHeaderCells(table);
    headers.forEach((th, index) => {
        if (!isHeaderSortable(th, table)) return;
        th.classList.add('ia-sortable-th');
        th.dataset.iaColumnIndex = String(index);
        th.tabIndex = 0;
        th.setAttribute('role', 'button');
        th.setAttribute('aria-sort', 'none');
        if (!th.querySelector('.ia-sort-indicator')) {
            const indicator = document.createElement('span');
            indicator.className = 'ia-sort-indicator bi bi-arrow-down-up';
            indicator.setAttribute('aria-hidden', 'true');
            th.appendChild(indicator);
        }
    });

    table.addEventListener('click', (event) => {
        const th = event.target.closest('th.ia-sortable-th');
        if (!th || !table.contains(th)) return;
        event.preventDefault();
        sortTableByHeader(table, th, event.shiftKey);
    });

    table.addEventListener('keydown', (event) => {
        const th = event.target.closest('th.ia-sortable-th');
        if (!th || !table.contains(th)) return;
        if (event.key === 'Enter' || event.key === ' ') {
            event.preventDefault();
            sortTableByHeader(table, th, event.shiftKey);
        }
    });

    table.dataset.iaSortingSetup = 'true';
}

function sortTableByHeader(table, th, additive) {
    const tbody = table.tBodies[0];
    if (!tbody) return;
    const index = Number(th.dataset.iaColumnIndex);
    const type = th.dataset.iaType || 'text';
    const current = SORT_STATE.get(table) || [];
    let next;

    if (additive) {
        next = current.filter((entry) => entry.index !== index);
        const existing = current.find((entry) => entry.index === index);
        next.push({ index, type, direction: existing?.direction === 'asc' ? 'desc' : 'asc' });
    } else {
        const existing = current.length === 1 && current[0].index === index ? current[0] : null;
        next = [{ index, type, direction: existing?.direction === 'asc' ? 'desc' : 'asc' }];
    }

    SORT_STATE.set(table, next);
    updateSortIndicators(table, next);

    const rows = Array.from(tbody.rows);
    const sortableRows = rows
        .map((row, originalIndex) => ({ row, originalIndex }))
        .filter(({ row }) => row.cells.length > 1 && !row.cells[0]?.hasAttribute('colspan'));

    sortableRows.sort((a, b) => compareRows(a, b, next));
    const fragment = document.createDocumentFragment();
    sortableRows.forEach(({ row }) => fragment.appendChild(row));
    tbody.appendChild(fragment);

    window.dispatchEvent(new CustomEvent('ia:table-sorted', { detail: { table, sort: next } }));
}

function updateSortIndicators(table, sortEntries) {
    const headers = tableHeaderCells(table);
    headers.forEach((th) => {
        const indicator = th.querySelector('.ia-sort-indicator');
        const priority = th.querySelector('.ia-sort-priority');
        if (priority) priority.remove();
        th.setAttribute('aria-sort', 'none');
        if (indicator) indicator.className = 'ia-sort-indicator bi bi-arrow-down-up';
    });

    sortEntries.forEach((entry, sortIndex) => {
        const th = headers[entry.index];
        if (!th) return;
        th.setAttribute('aria-sort', entry.direction === 'asc' ? 'ascending' : 'descending');
        const indicator = th.querySelector('.ia-sort-indicator');
        if (indicator) indicator.className = `ia-sort-indicator bi bi-arrow-${entry.direction === 'asc' ? 'up' : 'down'}`;
        if (sortEntries.length > 1) {
            const priority = document.createElement('span');
            priority.className = 'ia-sort-priority';
            priority.textContent = String(sortIndex + 1);
            th.appendChild(priority);
        }
    });
}

function compareRows(a, b, sortEntries) {
    for (const entry of sortEntries) {
        const av = sortValue(a.row.cells[entry.index], entry.type);
        const bv = sortValue(b.row.cells[entry.index], entry.type);
        let result = 0;
        if (av == null && bv != null) result = -1;
        else if (av != null && bv == null) result = 1;
        else if (typeof av === 'number' && typeof bv === 'number') result = av - bv;
        else result = String(av ?? '').localeCompare(String(bv ?? ''), undefined, { numeric: true, sensitivity: 'base' });
        if (result !== 0) return entry.direction === 'asc' ? result : -result;
    }
    return a.originalIndex - b.originalIndex;
}

function sortValue(cell, type) {
    if (!cell) return null;
    const dataValue = cell.dataset.sortValue || cell.querySelector('[data-sort-value]')?.dataset.sortValue;
    const raw = (dataValue || textOf(cell)).trim();
    if (!raw || EMPTY_VALUES.has(raw.toLowerCase())) return null;

    if (['number', 'count', 'progress', 'id'].includes(type)) {
        const n = Number(raw.replace(/[^0-9.-]+/g, ''));
        return Number.isFinite(n) ? n : raw.toLowerCase();
    }
    if (type === 'size') return parseSize(raw);
    if (['date', 'time', 'duration'].includes(type)) {
        const date = Date.parse(raw);
        if (Number.isFinite(date)) return date;
        const n = Number(raw.replace(/[^0-9.-]+/g, ''));
        return Number.isFinite(n) ? n : raw.toLowerCase();
    }
    return raw.toLowerCase();
}

function parseSize(raw) {
    const match = String(raw).toLowerCase().match(/([0-9]+(?:\.[0-9]+)?)\s*(b|bytes|kb|mb|gb|tb)?/);
    if (!match) return raw.toLowerCase();
    const value = Number(match[1]);
    const unit = match[2] || 'b';
    const multipliers = { b: 1, bytes: 1, kb: 1024, mb: 1024 ** 2, gb: 1024 ** 3, tb: 1024 ** 4 };
    return value * (multipliers[unit] || 1);
}

function setupSelectionFeedback(table) {
    if (table.dataset.iaSelectionSetup === 'true') return;
    const update = () => {
        table.querySelectorAll('tbody tr').forEach((row) => {
            const checked = !!row.querySelector('input[type="checkbox"]:checked');
            row.classList.toggle('is-selected', checked);
        });
    };
    table.addEventListener('change', (event) => {
        if (event.target.matches('input[type="checkbox"]')) update();
    });
    update();
    table.dataset.iaSelectionSetup = 'true';
}

function setupDynamicTableObserver(table) {
    if (TABLE_OBSERVERS.has(table)) return;
    const tbody = table.tBodies[0];
    if (!tbody) return;
    const observer = new MutationObserver(() => {
        applyColumnSemantics(table);
        refreshSortableHeaders(table);
        setupSelectionFeedback(table);
    });
    observer.observe(tbody, { childList: true, subtree: false });
    TABLE_OBSERVERS.set(table, observer);
}

function refreshSortableHeaders(table) {
    tableHeaderCells(table).forEach((th) => {
        if (th.dataset.iaColumnIndex && !isHeaderSortable(th, table)) {
            th.classList.remove('ia-sortable-th');
            th.removeAttribute('role');
            th.removeAttribute('tabindex');
            th.removeAttribute('aria-sort');
        } else if (!th.dataset.iaColumnIndex && isHeaderSortable(th, table)) {
            table.dataset.iaSortingSetup = 'false';
        }
    });
    if (table.dataset.iaSortingSetup === 'false') {
        delete table.dataset.iaSortingSetup;
        setupTableSorting(table);
    }
}

function enhanceTables(root = document) {
    const tables = root.matches?.(SELECTOR.tables) ? [root] : Array.from(root.querySelectorAll?.(SELECTOR.tables) || []);
    tables.forEach((table) => {
        if (!shouldEnhanceTable(table)) return;
        table.classList.add('ia-table');
        if (table.dataset[TABLE_ENHANCED] !== 'true') {
            table.dataset[TABLE_ENHANCED] = 'true';
            ensureTableWrapper(table);
            applyColumnSemantics(table);
            setupTableSorting(table);
            setupSelectionFeedback(table);
            setupDynamicTableObserver(table);
        } else {
            applyColumnSemantics(table);
            refreshSortableHeaders(table);
        }
    });
}

function modalIntentText(modal) {
    return [modal.id, textOf(modal.querySelector('.modal-title')), modal.querySelector('form')?.id]
        .filter(Boolean)
        .join(' ')
        .toLowerCase();
}

function isCreateOrEditModal(modal) {
    return /add|create|new|edit|save/.test(modalIntentText(modal));
}

function enhanceModals(root = document) {
    const modals = root.matches?.(SELECTOR.modals) ? [root] : Array.from(root.querySelectorAll?.(SELECTOR.modals) || []);
    modals.forEach((modal) => {
        if (!(modal instanceof HTMLElement)) return;
        modal.classList.add('ia-modal');
        if (isCreateOrEditModal(modal)) {
            modal.classList.add(/edit|update/.test(modalIntentText(modal)) ? 'ia-edit-modal' : 'ia-create-modal');
        }

        const forms = Array.from(modal.querySelectorAll('form'));
        forms.forEach((form) => enhanceForm(form, modal));

        if (modal.dataset[MODAL_ENHANCED] !== 'true') {
            modal.addEventListener('shown.bs.modal', () => {
                snapshotModalForms(modal);
                focusFirstField(modal);
            });
            modal.addEventListener('hide.bs.modal', (event) => {
                if (!hasUnsavedFormChanges(modal)) return;
                const message = window.translations?.discardUnsavedChanges || 'Discard unsaved changes?';
                if (window.confirm(message)) return;
                event.preventDefault();
            });
            modal.addEventListener('hidden.bs.modal', () => {
                modal.querySelectorAll('form').forEach((form) => {
                    form.classList.remove('was-validated');
                    form.querySelectorAll('.is-invalid, .is-valid').forEach((el) => el.classList.remove('is-invalid', 'is-valid'));
                    form.dataset.iaInitialValues = serializeForm(form);
                    delete form.dataset.iaSubmitting;
                });
            });
            modal.addEventListener('keydown', (event) => {
                if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') {
                    const primary = modal.querySelector('.modal-footer .btn-primary:not([disabled]), button[type="submit"]:not([disabled])');
                    if (primary) {
                        event.preventDefault();
                        primary.click();
                    }
                }
            });
            modal.dataset[MODAL_ENHANCED] = 'true';
        }
    });
}

function snapshotModalForms(modal) {
    modal.querySelectorAll('form').forEach((form) => {
        form.dataset.iaInitialValues = serializeForm(form);
        delete form.dataset.iaSubmitting;
    });
}

function serializeForm(form) {
    const values = [];
    Array.from(form.elements || []).forEach((element) => {
        if (!element.name && !element.id) return;
        if (element.disabled || ['button', 'submit', 'reset', 'file'].includes(element.type)) return;
        const key = element.name || element.id;
        if (element.type === 'checkbox' || element.type === 'radio') {
            values.push([key, element.checked ? '1' : '0']);
        } else {
            values.push([key, element.value || '']);
        }
    });
    return JSON.stringify(values);
}

function hasUnsavedFormChanges(modal) {
    if (!isCreateOrEditModal(modal)) return false;
    return Array.from(modal.querySelectorAll('form')).some((form) => {
        if (form.dataset.iaSubmitting === 'true') return false;
        const initial = form.dataset.iaInitialValues ?? serializeForm(form);
        return initial !== serializeForm(form);
    });
}

function markFormSubmitting(form, submitting = true) {
    if (!form) return;
    if (submitting) {
        form.dataset.iaSubmitting = 'true';
    } else {
        delete form.dataset.iaSubmitting;
    }
}

function enhanceForm(form, modal) {
    form.classList.add('ia-form');
    if (form.dataset[FORM_ENHANCED] === 'true') return;

    markRequiredFields(form);
    wireInlineValidation(form);
    wireButtonValidation(form, modal);
    wireEnterSubmit(form, modal);
    form.addEventListener('submit', (event) => {
        if (!form.checkValidity()) return;
        const submitter = event.submitter;
        if (submitter instanceof HTMLButtonElement || submitter instanceof HTMLInputElement) {
            if (submitter.dataset.iaClickLock === 'true') {
                event.preventDefault();
                event.stopImmediatePropagation();
                return;
            }
            submitter.dataset.iaClickLock = 'true';
            window.setTimeout(() => { delete submitter.dataset.iaClickLock; }, 1200);
        }
        markFormSubmitting(form, true);
        window.setTimeout(() => markFormSubmitting(form, false), 5000);
    });
    form.dataset[FORM_ENHANCED] = 'true';
}

function markRequiredFields(form) {
    Array.from(form.querySelectorAll('input[required], select[required], textarea[required]')).forEach((control) => {
        if (!control.id) return;
        const label = form.querySelector(`label[for="${CSS.escape(control.id)}"]`) || control.closest('.mb-3, .form-group, .col-md-12, .col-md-8, .col-md-6, .col-md-4, .col-12')?.querySelector('label');
        if (!label || label.dataset.iaRequiredMarked === 'true') return;
        label.classList.add('ia-label-required');
        if (!/\*/.test(label.textContent || '')) {
            const marker = document.createElement('span');
            marker.className = 'ia-required-mark';
            marker.setAttribute('aria-hidden', 'true');
            marker.textContent = '*';
            label.appendChild(marker);
        }
        label.dataset.iaRequiredMarked = 'true';
    });
}

function wireInlineValidation(form) {
    form.addEventListener('submit', (event) => {
        if (!form.checkValidity()) {
            event.preventDefault();
            event.stopPropagation();
            form.classList.add('was-validated');
            focusFirstInvalid(form);
        }
    });

    form.addEventListener('input', (event) => validateControl(event.target));
    form.addEventListener('change', (event) => validateControl(event.target));
}

function validateControl(control) {
    if (!(control instanceof HTMLInputElement || control instanceof HTMLSelectElement || control instanceof HTMLTextAreaElement)) return;
    if (!control.required && !control.value) return;
    if (control.checkValidity()) {
        control.classList.remove('is-invalid');
        if (control.value) control.classList.add('is-valid');
    } else {
        control.classList.remove('is-valid');
        control.classList.add('is-invalid');
    }
}

function wireButtonValidation(form, modal) {
    const buttons = Array.from(modal.querySelectorAll('.modal-footer button, .modal-footer .btn'));
    buttons.forEach((button) => {
        if (button.dataset.bsDismiss === 'modal' || button.type === 'submit') return;
        const action = `${button.getAttribute('onclick') || ''} ${textOf(button)}`;
        if (!/save|submit|create|add|update/i.test(action)) return;
        button.addEventListener('click', (event) => {
            if (form.checkValidity()) {
                if (button.dataset.iaClickLock === 'true') {
                    event.preventDefault();
                    event.stopImmediatePropagation();
                    return;
                }
                button.dataset.iaClickLock = 'true';
                window.setTimeout(() => { delete button.dataset.iaClickLock; }, 1200);
                markFormSubmitting(form, true);
                window.setTimeout(() => markFormSubmitting(form, false), 5000);
                return;
            }
            event.preventDefault();
            event.stopImmediatePropagation();
            form.classList.add('was-validated');
            focusFirstInvalid(form);
        }, true);
    });
}

function wireEnterSubmit(form, modal) {
    const hasAutocomplete = !!form.querySelector('[id$="SearchResults"], .word-search-results, .category-search-results');
    if (hasAutocomplete) return;
    form.addEventListener('keydown', (event) => {
        if (event.key !== 'Enter' || event.shiftKey || event.ctrlKey || event.metaKey || event.altKey) return;
        if (!(event.target instanceof HTMLInputElement || event.target instanceof HTMLSelectElement)) return;
        const primary = modal.querySelector('.modal-footer .btn-primary:not([disabled]), button[type="submit"]:not([disabled])');
        if (!primary) return;
        event.preventDefault();
        primary.click();
    });
}

function focusFirstInvalid(form) {
    const invalid = form.querySelector(':invalid');
    if (invalid && typeof invalid.focus === 'function') invalid.focus({ preventScroll: false });
}

function focusFirstField(modal) {
    if (modal.dataset.iaAutofocus === 'false') return;
    const alreadyFocused = modal.querySelector(':focus');
    if (alreadyFocused && alreadyFocused !== modal) return;
    const target = modal.querySelector('[autofocus], input:not([type="hidden"]):not([disabled]):not([readonly]), select:not([disabled]), textarea:not([disabled]):not([readonly])');
    if (target && typeof target.focus === 'function') {
        window.setTimeout(() => target.focus({ preventScroll: true }), 80);
    }
}

function enhanceExistingFilters(root = document) {
    Array.from(root.querySelectorAll?.('.file-filters-section, .action-bar, .results-info-bar') || []).forEach((el) => {
        el.classList.add(el.classList.contains('file-filters-section') ? 'ia-filter-panel' : 'ia-data-controls');
    });
}

function refresh(root = document) {
    enhanceExistingFilters(root);
    enhanceTables(root);
    enhanceModals(root);
}

function setButtonBusy(button, busy, options = {}) {
    if (!button) return;
    const form = button.closest?.('form');
    if (busy) {
        markFormSubmitting(form, true);
        if (!button.dataset.iaOriginalHtml) button.dataset.iaOriginalHtml = button.innerHTML;
        const label = options.label || textOf(button) || 'Saving';
        button.dataset.iaBusy = 'true';
        button.setAttribute('aria-busy', 'true');
        button.disabled = true;
        button.innerHTML = `<span class="ia-btn-spinner" aria-hidden="true"></span><span>${escapeHtml(label)}</span>`;
    } else {
        markFormSubmitting(form, false);
        button.dataset.iaBusy = 'false';
        button.removeAttribute('aria-busy');
        button.disabled = false;
        if (button.dataset.iaOriginalHtml) {
            button.innerHTML = button.dataset.iaOriginalHtml;
            delete button.dataset.iaOriginalHtml;
        }
    }
}

function highlightNewRecord(selectorOrElement) {
    const element = typeof selectorOrElement === 'string' ? document.querySelector(selectorOrElement) : selectorOrElement;
    if (!element) return;
    element.classList.add(element.tagName === 'TR' ? 'ia-row-new' : element.classList.contains('list-group-item') ? 'ia-list-row-new' : 'ia-card-new');
    element.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
    window.setTimeout(() => element.classList.remove('ia-row-new', 'ia-card-new', 'ia-list-row-new'), 2600);
}

function startBodyObserver() {
    const observer = new MutationObserver((mutations) => {
        const roots = new Set();
        mutations.forEach((mutation) => {
            mutation.addedNodes.forEach((node) => {
                if (node.nodeType === Node.ELEMENT_NODE) roots.add(node);
            });
        });
        roots.forEach((root) => refresh(root));
    });
    observer.observe(document.body, { childList: true, subtree: true });
}

function init() {
    refresh(document);
    startBodyObserver();
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init, { once: true });
} else {
    init();
}

window.InforaxisDataInterface = Object.freeze({
    refresh,
    setButtonBusy,
    highlightNewRecord,
    decorateRow,
    applyColumnSemantics,
    version: '2026.09.16'
});

export { refresh, setButtonBusy, highlightNewRecord };
