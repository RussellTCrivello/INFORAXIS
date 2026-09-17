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
const TABLE_WORKBENCHES = new WeakMap();
const STORAGE_KEYS = {
    density: 'inforaxis.workspace.density',
    theme: 'inforaxis.workspace.theme',
    commandHintDismissed: 'inforaxis.workspace.commandHintDismissed',
    tablePrefsPrefix: 'inforaxis.tablePrefs.',
    tableViewsPrefix: 'inforaxis.tableViews.'
};

const SELECTOR = {
    tables: 'table',
    modals: '.modal',
    controlSurfaces: [
        '.ia-control-surface',
        '[data-ia-role="controls"]',
        '[data-ia-sticky="true"]',
        '.file-filters-section',
        '.filter-panel',
        '.filters-panel',
        '.advanced-filters-panel',
        '.filters-chips-container',
        '.filter-actions-bar',
        '.search-command-card',
        '.search-filter-section',
        '.search-view-navigation',
        '.search-toolbar',
        '.search-toolbar-side',
        '.analysis-view-navigation',
        '.dashboard-navigation',
        '.tab-navigation',
        '.path-tree-actions',
        '.analyst-classify-controls',
        '.analyst-filters',
        '.analyst-pagination',
        '.chart-controls-wrapper',
        '.chart-toolbar',
        '.chart-actions',
        '.upload-controls',
        '.navigation-bar',
        '.fmas-global-search-bar',
        '.file-section-toolbar',
        '.file-content-actions',
        '.file-modal-nav-controls',
        '.modal-search-row',
        '.sort-control',
        '.per-page-control',
        '.action-bar',
        '.results-info-bar',
        '.results-actions',
        '.results-sort',
        '.results-pagination',
        '.pagination-container',
        '.pagination-wrapper',
        '.unified-pagination-container',
        '.cursor-pagination-container',
        '.pagination-controls',
        '.unified-pagination-controls',
        '.paging-controls'
    ].join(','),
    dataRegions: [
        '.ia-scroll-body',
        '[data-ia-role="data-region"]',
        '[data-ia-scroll="true"]',
        '.table-wrapper',
        '.table-responsive',
        '.ia-table-scroll',
        '.results-container',
        '.search-results-container',
        '.similar-groups-container',
        '.files-list-view',
        '.files-grid-view',
        '.explorer-grid',
        '.source-linkage-grid',
        '.categories-grid',
        '.keywords-grid',
        '.cards-grid',
        '.ia-record-list',
        '.files-grid',
        '.files-container',
        '.data-grid',
        '.result-list',
        '.results-list',
        '.results-grid',
        '.search-results-card',
        '.file-reports-grid',
        '.notifications-list',
        '.path-tree',
        '.path-tree-container',
        '.word-search-results',
        '.category-search-results'
    ].join(','),
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

function readStoredJSON(key, fallback = null) {
    const storage = safeLocalStorage();
    if (!storage) return fallback;
    try {
        const value = storage.getItem(key);
        return value ? JSON.parse(value) : fallback;
    } catch (error) {
        console.warn('Could not read stored workspace preference', key, error);
        return fallback;
    }
}

function writeStoredJSON(key, value) {
    const storage = safeLocalStorage();
    if (!storage) return;
    try {
        storage.setItem(key, JSON.stringify(value));
    } catch (error) {
        console.warn('Could not store workspace preference', key, error);
    }
}

function debounce(fn, delay = 160) {
    let timer;
    return (...args) => {
        window.clearTimeout(timer);
        timer = window.setTimeout(() => fn(...args), delay);
    };
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

function queryWithin(root, selector) {
    const elements = [];
    if (root?.matches?.(selector)) elements.push(root);
    elements.push(...Array.from(root?.querySelectorAll?.(selector) || []));
    return elements;
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
        existing.classList.add('ia-table-scroll', 'ia-data-scroll-region');
        if (!existing.getAttribute('role')) existing.setAttribute('role', 'region');
        if (!existing.getAttribute('aria-label')) {
            const heading = existing.closest('.section-card, .stat-card, .card')?.querySelector('h1,h2,h3,h4,h5,h6');
            if (heading) existing.setAttribute('aria-label', textOf(heading));
        }
        return existing;
    }

    const wrapper = document.createElement('div');
    wrapper.className = 'ia-table-scroll ia-data-scroll-region';
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
    tbody.querySelectorAll('.ia-row-detail').forEach((detailRow) => detailRow.remove());
    tbody.querySelectorAll('tr[aria-expanded="true"]').forEach((row) => row.setAttribute('aria-expanded', 'false'));
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

    sortRowsByState(table, next);

    updateWorkbenchMetrics(table);
    persistTablePreferences(table);
    window.dispatchEvent(new CustomEvent('ia:table-sorted', { detail: { table, sort: next } }));
}

function sortRowsByState(table, sortEntries) {
    const tbody = table.tBodies[0];
    if (!tbody || !sortEntries.length) return;
    tbody.querySelectorAll('.ia-row-detail').forEach((detailRow) => detailRow.remove());
    tbody.querySelectorAll('tr[aria-expanded="true"]').forEach((row) => row.setAttribute('aria-expanded', 'false'));
    const sortableRows = Array.from(tbody.rows)
        .map((row, originalIndex) => ({ row, originalIndex }))
        .filter(({ row }) => row.cells.length > 1 && !row.classList.contains('ia-row-detail') && !row.cells[0]?.hasAttribute('colspan'));

    sortableRows.sort((a, b) => compareRows(a, b, sortEntries));
    const fragment = document.createDocumentFragment();
    sortableRows.forEach(({ row }) => fragment.appendChild(row));
    tbody.appendChild(fragment);
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
        applyColumnVisibility(table);
        tableDataRows(table).forEach((row) => {
            row.tabIndex = 0;
            if (!row.hasAttribute('aria-expanded')) row.setAttribute('aria-expanded', 'false');
        });
        filterTableRows(table, table.dataset.iaFilterQuery || '');
        ensureTableWorkbench(table, closestTableWrapper(table) || ensureTableWrapper(table));
        updateWorkbenchMetrics(table);
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


function tableDataRows(table) {
    return Array.from(table.tBodies || [])
        .flatMap((tbody) => Array.from(tbody.rows))
        .filter((row) => row.cells.length > 1 && !row.classList.contains('ia-row-detail') && !row.cells[0]?.hasAttribute('colspan'));
}

function tableKey(table) {
    if (table.dataset.iaKey) return table.dataset.iaKey;
    const explicit = table.dataset.iaTable || table.id || table.getAttribute('aria-label') || '';
    const tables = Array.from(document.querySelectorAll('table'));
    const index = Math.max(0, tables.indexOf(table));
    const key = `${window.location.pathname}::${explicit || `table-${index}`}`.replace(/[^a-z0-9:_/.-]+/gi, '-');
    table.dataset.iaKey = key;
    if (!table.id) table.id = `ia-table-${index + 1}`;
    return key;
}

function tableTitle(table) {
    return table.caption?.textContent?.trim()
        || table.dataset.iaTitle
        || table.closest('.section-card, .stat-card, .card, main')?.querySelector('h1,h2,h3,h4,h5,h6')?.textContent?.trim()
        || 'Data table';
}

function shouldShowTableWorkbench(table) {
    if (table.dataset.iaToolbar === 'false') return false;
    if (table.closest('.modal')) return false;
    if (table.dataset.iaToolbar === 'true') return true;
    const headers = tableHeaderCells(table).filter((th) => textOf(th));
    return headers.length >= 3 && tableDataRows(table).length >= 3;
}

function tablePrefsKey(table) {
    return STORAGE_KEYS.tablePrefsPrefix + tableKey(table);
}

function tableViewsKey(table) {
    return STORAGE_KEYS.tableViewsPrefix + tableKey(table);
}

function getHiddenColumns(table) {
    try {
        const parsed = JSON.parse(table.dataset.iaHiddenColumns || '[]');
        return Array.isArray(parsed) ? parsed.map(Number).filter(Number.isFinite) : [];
    } catch (error) {
        return [];
    }
}

function setHiddenColumns(table, indexes) {
    const unique = Array.from(new Set((indexes || []).map(Number).filter(Number.isFinite))).sort((a, b) => a - b);
    table.dataset.iaHiddenColumns = JSON.stringify(unique);
    applyColumnVisibility(table);
    updateWorkbenchMetrics(table);
    persistTablePreferences(table);
}

function visibleColumnCount(table) {
    const hidden = new Set(getHiddenColumns(table));
    const count = tableHeaderCells(table).filter((_, index) => !hidden.has(index)).length;
    return Math.max(count, 1);
}

function applyColumnVisibility(table) {
    const hidden = new Set(getHiddenColumns(table));
    const headers = tableHeaderCells(table);
    headers.forEach((header, index) => {
        const isHidden = hidden.has(index);
        header.hidden = isHidden;
        header.setAttribute('aria-hidden', isHidden ? 'true' : 'false');
    });
    Array.from(table.tBodies || []).forEach((tbody) => {
        Array.from(tbody.rows).forEach((row) => {
            if (row.classList.contains('ia-row-detail')) {
                const detailCell = row.cells[0];
                if (detailCell) detailCell.colSpan = visibleColumnCount(table);
                return;
            }
            Array.from(row.cells).forEach((cell, index) => {
                const isHidden = hidden.has(index);
                cell.hidden = isHidden;
                cell.setAttribute('aria-hidden', isHidden ? 'true' : 'false');
            });
        });
    });
}

function groupForColumnType(type) {
    if (['select', 'id'].includes(type)) return 'Identity';
    if (['number', 'count', 'size', 'progress', 'duration'].includes(type)) return 'Metrics';
    if (['date', 'time'].includes(type)) return 'Time';
    if (['status', 'tag'].includes(type)) return 'Classification';
    if (type === 'actions') return 'Actions';
    return 'Attributes';
}

function columnGroups(table) {
    const groups = new Map();
    tableHeaderCells(table).forEach((header, index) => {
        const type = header.dataset.iaType || inferColumnType(textOf(header), index, header);
        const group = groupForColumnType(type);
        if (!groups.has(group)) groups.set(group, []);
        groups.get(group).push({ index, label: textOf(header) || `Column ${index + 1}`, type });
    });
    return groups;
}

function renderColumnPanel(table, panel) {
    const hidden = new Set(getHiddenColumns(table));
    const groups = columnGroups(table);
    panel.innerHTML = Array.from(groups.entries()).map(([group, columns]) => `
        <fieldset class="ia-column-group">
            <legend>${escapeHtml(group)}</legend>
            ${columns.map((column) => `
                <label class="ia-column-choice">
                    <input type="checkbox" data-ia-column-index="${column.index}" ${hidden.has(column.index) ? '' : 'checked'} ${column.type === 'actions' || column.type === 'select' ? 'data-ia-essential="true"' : ''}>
                    <span>${escapeHtml(column.label)}</span>
                    <em>${escapeHtml(column.type)}</em>
                </label>`).join('')}
        </fieldset>`).join('');
}

function filterTableRows(table, query = '') {
    const normalized = String(query || '').trim().toLowerCase();
    table.dataset.iaFilterQuery = normalized;
    const terms = normalized.split(/\s+/).filter(Boolean);
    tableDataRows(table).forEach((row) => {
        const matches = !terms.length || terms.every((term) => textOf(row).toLowerCase().includes(term));
        if (!matches) {
            row.hidden = true;
            row.dataset.iaSearchHidden = 'true';
        } else if (row.dataset.iaSearchHidden === 'true') {
            row.hidden = false;
            delete row.dataset.iaSearchHidden;
        }
        const detail = row.nextElementSibling;
        if (detail?.classList.contains('ia-row-detail')) detail.hidden = row.hidden;
    });
    updateWorkbenchMetrics(table);
    persistTablePreferences(table);
}

function sortedSummary(table) {
    const sortEntries = SORT_STATE.get(table) || [];
    if (!sortEntries.length) return '';
    const headers = tableHeaderCells(table);
    return sortEntries.map((entry, index) => {
        const label = textOf(headers[entry.index]) || `Column ${entry.index + 1}`;
        return `${sortEntries.length > 1 ? `${index + 1}. ` : ''}${label} ${entry.direction === 'asc' ? '↑' : '↓'}`;
    }).join(' · ');
}

function updateWorkbenchMetrics(table) {
    const toolbar = TABLE_WORKBENCHES.get(table) || document.querySelector(`[data-ia-workbench-for="${CSS.escape(tableKey(table))}"]`);
    if (!toolbar) return;
    const rows = tableDataRows(table);
    const visible = rows.filter((row) => !row.hidden).length;
    const count = toolbar.querySelector('[data-ia-row-count]');
    if (count) count.textContent = `${visible.toLocaleString()} / ${rows.length.toLocaleString()} rows`;
    const summary = toolbar.querySelector('[data-ia-sort-summary]');
    if (summary) {
        const text = sortedSummary(table);
        summary.textContent = text ? `Sorted: ${text}` : 'Unsorted';
    }
}

function currentTablePreferences(table) {
    return {
        hiddenColumns: getHiddenColumns(table),
        filterQuery: table.dataset.iaFilterQuery || '',
        sort: SORT_STATE.get(table) || [],
        density: document.body.dataset.iaDensity || 'comfortable'
    };
}

function persistTablePreferences(table) {
    writeStoredJSON(tablePrefsKey(table), currentTablePreferences(table));
}

function applyTablePreferences(table, prefs = {}, toolbar = TABLE_WORKBENCHES.get(table)) {
    if (!prefs || typeof prefs !== 'object') return;
    if (Array.isArray(prefs.hiddenColumns)) {
        table.dataset.iaHiddenColumns = JSON.stringify(prefs.hiddenColumns);
        applyColumnVisibility(table);
        const panel = toolbar?.querySelector('.ia-columns-panel');
        if (panel) renderColumnPanel(table, panel);
    }
    if (typeof prefs.filterQuery === 'string') {
        const search = toolbar?.querySelector('.ia-table-search');
        if (search) search.value = prefs.filterQuery;
        filterTableRows(table, prefs.filterQuery);
    }
    if (Array.isArray(prefs.sort) && prefs.sort.length) {
        SORT_STATE.set(table, prefs.sort);
        updateSortIndicators(table, prefs.sort);
        sortRowsByState(table, prefs.sort);
    }
    if (prefs.density) applyDensity(prefs.density, false);
    updateWorkbenchMetrics(table);
}

function loadSavedViews(table) {
    const views = readStoredJSON(tableViewsKey(table), []);
    return Array.isArray(views) ? views.filter((view) => view && view.name && view.preferences) : [];
}

function populateSavedViews(table, select) {
    if (!select) return;
    const current = select.value;
    select.innerHTML = '<option value="__default__">Default view</option>';
    loadSavedViews(table).forEach((view, index) => {
        select.appendChild(new Option(view.name, String(index)));
    });
    if (Array.from(select.options).some((option) => option.value === current)) select.value = current;
}

function saveCurrentView(table, select) {
    const name = window.prompt('Name this table view:', `${tableTitle(table)} view`);
    const trimmed = (name || '').trim();
    if (!trimmed) return;
    const views = loadSavedViews(table).filter((view) => view.name !== trimmed);
    views.push({ name: trimmed, preferences: currentTablePreferences(table), savedAt: new Date().toISOString() });
    writeStoredJSON(tableViewsKey(table), views);
    populateSavedViews(table, select);
    if (select) select.value = String(views.length - 1);
}

function resetTableWorkbench(table) {
    SORT_STATE.set(table, []);
    updateSortIndicators(table, []);
    setHiddenColumns(table, []);
    filterTableRows(table, '');
    const toolbar = TABLE_WORKBENCHES.get(table);
    if (toolbar) {
        const search = toolbar.querySelector('.ia-table-search');
        if (search) search.value = '';
        const saved = toolbar.querySelector('.ia-saved-view-select');
        if (saved) saved.value = '__default__';
        const panel = toolbar.querySelector('.ia-columns-panel');
        if (panel) renderColumnPanel(table, panel);
    }
    persistTablePreferences(table);
}

function densityOptionsMarkup(activeDensity) {
    return ['compact', 'comfortable', 'spacious'].map((density) => `
        <button type="button" class="ia-density-btn ${density === activeDensity ? 'is-active' : ''}" data-ia-density-choice="${density}" aria-pressed="${density === activeDensity ? 'true' : 'false'}">
            ${density === 'compact' ? 'Compact' : density === 'spacious' ? 'Spacious' : 'Comfort'}
        </button>`).join('');
}

function ensureTableWorkbench(table, wrapper) {
    if (!shouldShowTableWorkbench(table)) return null;
    const key = tableKey(table);
    const existing = wrapper.previousElementSibling?.matches?.(`[data-ia-workbench-for="${CSS.escape(key)}"]`) ? wrapper.previousElementSibling : null;
    if (existing) {
        TABLE_WORKBENCHES.set(table, existing);
        updateWorkbenchMetrics(table);
        return existing;
    }

    const toolbar = document.createElement('div');
    toolbar.className = 'ia-table-workbench';
    toolbar.dataset.iaWorkbenchFor = key;
    toolbar.setAttribute('aria-label', `${tableTitle(table)} controls`);
    toolbar.innerHTML = `
        <div class="ia-workbench-row ia-workbench-primary">
            <label class="ia-table-search-field">
                <i class="bi bi-search" aria-hidden="true"></i>
                <input type="search" class="ia-table-search" placeholder="Search visible rows" aria-label="Search ${escapeAttr(tableTitle(table))}">
            </label>
            <div class="ia-workbench-actions">
                <button type="button" class="ia-workbench-btn" data-ia-action="toggle-columns" aria-expanded="false">
                    <i class="bi bi-layout-three-columns" aria-hidden="true"></i><span>Columns</span>
                </button>
                <select class="ia-saved-view-select" aria-label="Saved table views"></select>
                <button type="button" class="ia-workbench-btn" data-ia-action="save-view">
                    <i class="bi bi-bookmark-plus" aria-hidden="true"></i><span>Save view</span>
                </button>
                <div class="ia-density-segment" role="group" aria-label="Table density">
                    ${densityOptionsMarkup(document.body.dataset.iaDensity || 'comfortable')}
                </div>
                <button type="button" class="ia-workbench-btn ia-workbench-btn-subtle" data-ia-action="reset-view">
                    <i class="bi bi-arrow-counterclockwise" aria-hidden="true"></i><span>Reset</span>
                </button>
            </div>
        </div>
        <div class="ia-workbench-row ia-workbench-secondary">
            <span class="ia-workbench-metric" data-ia-row-count></span>
            <span class="ia-workbench-metric" data-ia-sort-summary>Unsorted</span>
            <span class="ia-workbench-help">Shift-click headers for multi-sort · Alt+Enter opens row details</span>
        </div>
        <div class="ia-columns-panel" hidden></div>`;

    const panel = toolbar.querySelector('.ia-columns-panel');
    renderColumnPanel(table, panel);
    const savedSelect = toolbar.querySelector('.ia-saved-view-select');
    populateSavedViews(table, savedSelect);

    const searchInput = toolbar.querySelector('.ia-table-search');
    searchInput.addEventListener('input', debounce(() => filterTableRows(table, searchInput.value), 140));

    toolbar.addEventListener('click', (event) => {
        const actionButton = event.target.closest('[data-ia-action]');
        if (actionButton) {
            const action = actionButton.dataset.iaAction;
            if (action === 'toggle-columns') {
                const isHidden = panel.hidden;
                panel.hidden = !isHidden;
                actionButton.setAttribute('aria-expanded', String(isHidden));
            }
            if (action === 'save-view') saveCurrentView(table, savedSelect);
            if (action === 'reset-view') resetTableWorkbench(table);
            return;
        }

        const densityButton = event.target.closest('[data-ia-density-choice]');
        if (densityButton) {
            applyDensity(densityButton.dataset.iaDensityChoice);
            toolbar.querySelectorAll('[data-ia-density-choice]').forEach((button) => {
                const active = button === densityButton;
                button.classList.toggle('is-active', active);
                button.setAttribute('aria-pressed', String(active));
            });
            persistTablePreferences(table);
        }
    });

    panel.addEventListener('change', (event) => {
        const checkbox = event.target.closest('input[data-ia-column-index]');
        if (!checkbox) return;
        const hidden = new Set(getHiddenColumns(table));
        const index = Number(checkbox.dataset.iaColumnIndex);
        if (checkbox.checked) hidden.delete(index);
        else hidden.add(index);
        setHiddenColumns(table, Array.from(hidden));
    });

    savedSelect.addEventListener('change', () => {
        if (savedSelect.value === '__default__') {
            resetTableWorkbench(table);
            return;
        }
        const view = loadSavedViews(table)[Number(savedSelect.value)];
        if (view) applyTablePreferences(table, view.preferences, toolbar);
    });

    wrapper.parentNode.insertBefore(toolbar, wrapper);
    TABLE_WORKBENCHES.set(table, toolbar);
    applyTablePreferences(table, readStoredJSON(tablePrefsKey(table), {}), toolbar);
    updateWorkbenchMetrics(table);
    return toolbar;
}

function setupTableKeyboard(table) {
    if (table.dataset.iaKeyboardSetup === 'true') return;
    const refreshRows = () => {
        tableDataRows(table).forEach((row) => {
            row.tabIndex = 0;
            if (!row.hasAttribute('aria-expanded')) row.setAttribute('aria-expanded', 'false');
        });
    };
    refreshRows();

    table.addEventListener('keydown', (event) => {
        const row = event.target.closest?.('tbody tr');
        if (!row || row.classList.contains('ia-row-detail') || !table.contains(row)) return;
        if (event.target.closest('input, select, textarea, button, a')) return;
        const rows = tableDataRows(table).filter((candidate) => !candidate.hidden);
        const index = rows.indexOf(row);
        if (index < 0) return;
        if (event.key === 'ArrowDown' || event.key === 'ArrowUp' || event.key === 'Home' || event.key === 'End') {
            event.preventDefault();
            const nextIndex = event.key === 'Home' ? 0 : event.key === 'End' ? rows.length - 1 : Math.max(0, Math.min(rows.length - 1, index + (event.key === 'ArrowDown' ? 1 : -1)));
            rows[nextIndex]?.focus({ preventScroll: false });
        }
        if ((event.key === 'Enter' && event.altKey) || (event.key === 'ArrowRight' && event.altKey)) {
            event.preventDefault();
            toggleRowDetail(table, row);
        }
    });

    table.addEventListener('dblclick', (event) => {
        const row = event.target.closest?.('tbody tr');
        if (!row || row.classList.contains('ia-row-detail') || event.target.closest('input, select, textarea, button, a')) return;
        toggleRowDetail(table, row);
    });

    const observer = TABLE_OBSERVERS.get(table);
    if (observer) {
        // existing observer already refreshes semantics; keyboard rows are cheap to refresh now
        refreshRows();
    }
    table.dataset.iaKeyboardSetup = 'true';
}

function toggleRowDetail(table, row) {
    const next = row.nextElementSibling;
    if (next?.classList.contains('ia-row-detail')) {
        next.remove();
        row.setAttribute('aria-expanded', 'false');
        return;
    }
    table.querySelectorAll('.ia-row-detail').forEach((detailRow) => detailRow.remove());
    table.querySelectorAll('tbody tr[aria-expanded="true"]').forEach((expandedRow) => expandedRow.setAttribute('aria-expanded', 'false'));

    const headers = tableHeaderCells(table);
    const hidden = new Set(getHiddenColumns(table));
    const details = headers.map((header, index) => {
        if (hidden.has(index)) return '';
        const type = header.dataset.iaType || 'text';
        if (['select', 'actions'].includes(type)) return '';
        const value = textOf(row.cells[index]);
        if (!value || EMPTY_VALUES.has(value.toLowerCase())) return '';
        return `<div class="ia-row-detail-item"><dt>${escapeHtml(textOf(header) || `Column ${index + 1}`)}</dt><dd>${escapeHtml(value)}</dd></div>`;
    }).filter(Boolean).join('');
    if (!details) return;

    const detailRow = document.createElement('tr');
    detailRow.className = 'ia-row-detail';
    detailRow.innerHTML = `<td colspan="${visibleColumnCount(table)}"><dl class="ia-row-detail-grid">${details}</dl></td>`;
    row.after(detailRow);
    row.setAttribute('aria-expanded', 'true');
}

function enhanceTables(root = document) {
    const tables = root.matches?.(SELECTOR.tables) ? [root] : Array.from(root.querySelectorAll?.(SELECTOR.tables) || []);
    tables.forEach((table) => {
        if (!shouldEnhanceTable(table)) return;
        table.classList.add('ia-table');
        if (table.dataset[TABLE_ENHANCED] !== 'true') {
            table.dataset[TABLE_ENHANCED] = 'true';
            const wrapper = ensureTableWrapper(table);
            applyColumnSemantics(table);
            setupTableSorting(table);
            setupSelectionFeedback(table);
            setupDynamicTableObserver(table);
            setupTableKeyboard(table);
            applyColumnVisibility(table);
            ensureTableWorkbench(table, wrapper);
        } else {
            applyColumnSemantics(table);
            refreshSortableHeaders(table);
            applyColumnVisibility(table);
            ensureTableWorkbench(table, closestTableWrapper(table) || ensureTableWrapper(table));
            updateWorkbenchMetrics(table);
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


function applyDensity(density = 'comfortable', persist = true) {
    const allowed = new Set(['compact', 'comfortable', 'spacious']);
    const next = allowed.has(density) ? density : 'comfortable';
    document.body.dataset.iaDensity = next;
    if (persist) {
        const storage = safeLocalStorage();
        try { storage?.setItem(STORAGE_KEYS.density, next); } catch (error) { /* ignore */ }
    }
    document.querySelectorAll('[data-ia-density-choice]').forEach((button) => {
        const active = button.dataset.iaDensityChoice === next;
        button.classList.toggle('is-active', active);
        button.setAttribute('aria-pressed', String(active));
    });
}

function resolvedWorkspaceTheme(mode) {
    if (mode === 'dark') return 'dark';
    if (mode === 'light') return 'light';
    return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}

function applyWorkspaceTheme(mode = 'system', persist = true) {
    const allowed = new Set(['light', 'dark', 'system']);
    const next = allowed.has(mode) ? mode : 'system';
    const resolved = resolvedWorkspaceTheme(next);
    document.body.dataset.iaThemePreference = next;
    document.body.dataset.iaTheme = resolved;
    document.body.classList.toggle('ia-theme-dark', resolved === 'dark');
    document.body.classList.toggle('ia-theme-light', resolved !== 'dark');
    if (persist) {
        const storage = safeLocalStorage();
        try { storage?.setItem(STORAGE_KEYS.theme, next); } catch (error) { /* ignore */ }
    }
}

function resetWorkspacePreferences() {
    const storage = safeLocalStorage();
    if (storage) {
        try {
            Array.from({ length: storage.length }, (_, index) => storage.key(index))
                .filter(Boolean)
                .filter((key) => key.startsWith(STORAGE_KEYS.tablePrefsPrefix) || key.startsWith(STORAGE_KEYS.tableViewsPrefix) || key === STORAGE_KEYS.density || key === STORAGE_KEYS.theme)
                .forEach((key) => storage.removeItem(key));
        } catch (error) {
            console.warn('Could not reset workspace preferences', error);
        }
    }
    applyDensity('comfortable', false);
    applyWorkspaceTheme('system', false);
    document.querySelectorAll('table.ia-table').forEach((table) => resetTableWorkbench(table));
}

function initializeWorkspaceShell() {
    document.body.classList.add('ia-workspace');
    const storage = safeLocalStorage();
    let density = 'comfortable';
    let theme = 'system';
    try {
        density = storage?.getItem(STORAGE_KEYS.density) || density;
        theme = storage?.getItem(STORAGE_KEYS.theme) || theme;
    } catch (error) {
        // ignore preference read errors
    }
    applyDensity(density, false);
    applyWorkspaceTheme(theme, false);
    window.matchMedia?.('(prefers-color-scheme: dark)').addEventListener?.('change', () => {
        if ((document.body.dataset.iaThemePreference || 'system') === 'system') applyWorkspaceTheme('system', false);
    });
    setupCommandPalette();
    setupGlobalSelectionContext();
}

function collectCommandPaletteItems() {
    const commands = [
        {
            title: 'Focus table search',
            meta: 'Workspace',
            icon: 'bi-search',
            action: () => document.querySelector('.ia-table-search, input[type="search"], input[id*="Search"], input[id*="search"]')?.focus({ preventScroll: false })
        },
        { title: 'Use compact density', meta: 'Workspace', icon: 'bi-list-ul', action: () => applyDensity('compact') },
        { title: 'Use comfortable density', meta: 'Workspace', icon: 'bi-view-list', action: () => applyDensity('comfortable') },
        { title: 'Use spacious density', meta: 'Workspace', icon: 'bi-distribute-vertical', action: () => applyDensity('spacious') },
        { title: 'Switch to light theme', meta: 'Theme', icon: 'bi-sun', action: () => applyWorkspaceTheme('light') },
        { title: 'Switch to dark theme', meta: 'Theme', icon: 'bi-moon-stars', action: () => applyWorkspaceTheme('dark') },
        { title: 'Use system theme', meta: 'Theme', icon: 'bi-circle-half', action: () => applyWorkspaceTheme('system') },
        { title: 'Reset workspace preferences', meta: 'Workspace', icon: 'bi-arrow-counterclockwise', action: resetWorkspacePreferences }
    ];

    document.querySelectorAll('.sidebar a[href], .navbar a[href], a.nav-link[href]').forEach((link) => {
        const title = textOf(link);
        const href = link.getAttribute('href');
        if (!title || !href || href === '#' || href.startsWith('javascript:')) return;
        commands.push({ title, meta: 'Navigate', icon: 'bi-arrow-right-circle', action: () => { window.location.href = href; } });
    });

    document.querySelectorAll('button, a.btn, [role="button"]').forEach((button) => {
        if (button.offsetParent === null) return;
        const title = textOf(button);
        if (!title || title.length > 64) return;
        if (!/add|create|new|import|export|save|upload|filter|analyze|analysis/i.test(title)) return;
        if (button.closest('.ia-command-palette, .ia-context-bar')) return;
        commands.push({
            title,
            meta: 'Action',
            icon: /add|create|new/i.test(title) ? 'bi-plus-circle' : /export|download/i.test(title) ? 'bi-download' : 'bi-lightning-charge',
            action: () => button.click()
        });
    });

    return commands;
}

function ensureCommandPalette() {
    let palette = document.getElementById('iaCommandPalette');
    if (palette) return palette;
    palette = document.createElement('div');
    palette.id = 'iaCommandPalette';
    palette.className = 'ia-command-palette';
    palette.hidden = true;
    palette.innerHTML = `
        <div class="ia-command-backdrop" data-ia-command-close></div>
        <section class="ia-command-dialog" role="dialog" aria-modal="true" aria-labelledby="iaCommandTitle">
            <div class="ia-command-search-row">
                <i class="bi bi-command" aria-hidden="true"></i>
                <input type="search" id="iaCommandInput" autocomplete="off" placeholder="Search commands, pages, and actions" aria-label="Search commands">
                <kbd>Esc</kbd>
            </div>
            <h2 id="iaCommandTitle" class="visually-hidden">Command palette</h2>
            <div class="ia-command-results" role="listbox" aria-label="Command results"></div>
            <div class="ia-command-footer"><span>↑↓ navigate</span><span>Enter run</span><span>⌘K / Ctrl K open</span></div>
        </section>`;
    document.body.appendChild(palette);
    return palette;
}

function renderCommandPalette(query = '') {
    const palette = ensureCommandPalette();
    const results = palette.querySelector('.ia-command-results');
    const items = collectCommandPaletteItems();
    const terms = query.trim().toLowerCase().split(/\s+/).filter(Boolean);
    const filtered = items.filter((item) => terms.every((term) => `${item.title} ${item.meta}`.toLowerCase().includes(term))).slice(0, 18);
    results.innerHTML = filtered.length ? filtered.map((item, index) => `
        <button type="button" class="ia-command-item ${index === 0 ? 'is-active' : ''}" role="option" data-ia-command-index="${index}">
            <i class="bi ${escapeAttr(item.icon)}" aria-hidden="true"></i>
            <span><strong>${escapeHtml(item.title)}</strong><small>${escapeHtml(item.meta)}</small></span>
        </button>`).join('') : '<div class="ia-command-empty">No matching commands</div>';
    palette._iaCommands = filtered;
}

function openCommandPalette() {
    const palette = ensureCommandPalette();
    palette.hidden = false;
    document.body.classList.add('ia-command-open');
    const input = palette.querySelector('#iaCommandInput');
    input.value = '';
    renderCommandPalette('');
    window.setTimeout(() => input.focus({ preventScroll: true }), 30);
}

function closeCommandPalette() {
    const palette = ensureCommandPalette();
    palette.hidden = true;
    document.body.classList.remove('ia-command-open');
}

function moveCommandSelection(direction) {
    const palette = ensureCommandPalette();
    const items = Array.from(palette.querySelectorAll('.ia-command-item'));
    if (!items.length) return;
    const activeIndex = Math.max(0, items.findIndex((item) => item.classList.contains('is-active')));
    const nextIndex = (activeIndex + direction + items.length) % items.length;
    items.forEach((item, index) => item.classList.toggle('is-active', index === nextIndex));
    items[nextIndex].scrollIntoView({ block: 'nearest' });
}

function runSelectedCommand() {
    const palette = ensureCommandPalette();
    const active = palette.querySelector('.ia-command-item.is-active');
    if (!active) return;
    const index = Number(active.dataset.iaCommandIndex || 0);
    const command = palette._iaCommands?.[index];
    if (!command) return;
    closeCommandPalette();
    command.action();
}

function injectCommandTrigger() {
    const header = document.querySelector('.page-header');
    if (!header || header.querySelector('.ia-command-trigger')) return;
    const trigger = document.createElement('button');
    trigger.type = 'button';
    trigger.className = 'ia-command-trigger';
    trigger.innerHTML = '<i class="bi bi-command" aria-hidden="true"></i><span>Command</span><kbd>⌘K</kbd>';
    trigger.addEventListener('click', openCommandPalette);
    header.appendChild(trigger);
}

function setupCommandPalette() {
    if (document.body.dataset.iaCommandSetup === 'true') return;
    const palette = ensureCommandPalette();
    const input = palette.querySelector('#iaCommandInput');
    input.addEventListener('input', () => renderCommandPalette(input.value));
    document.addEventListener('click', (event) => {
        if (event.target.closest('[data-ia-open-command]')) {
            event.preventDefault();
            openCommandPalette();
        }
    });
    palette.addEventListener('click', (event) => {
        if (event.target.closest('[data-ia-command-close]')) closeCommandPalette();
        const item = event.target.closest('.ia-command-item');
        if (item) {
            palette.querySelectorAll('.ia-command-item').forEach((el) => el.classList.toggle('is-active', el === item));
            runSelectedCommand();
        }
    });
    document.addEventListener('keydown', (event) => {
        const isCommandShortcut = (event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k';
        if (isCommandShortcut) {
            event.preventDefault();
            openCommandPalette();
            return;
        }
        if (palette.hidden) return;
        if (event.key === 'Escape') {
            event.preventDefault();
            closeCommandPalette();
        } else if (event.key === 'ArrowDown') {
            event.preventDefault();
            moveCommandSelection(1);
        } else if (event.key === 'ArrowUp') {
            event.preventDefault();
            moveCommandSelection(-1);
        } else if (event.key === 'Enter') {
            event.preventDefault();
            runSelectedCommand();
        }
    });
    injectCommandTrigger();
    document.body.dataset.iaCommandSetup = 'true';
}

function ensureContextualActionBar() {
    let bar = document.getElementById('iaContextBar');
    if (bar) return bar;
    bar = document.createElement('div');
    bar.id = 'iaContextBar';
    bar.className = 'ia-context-bar';
    bar.hidden = true;
    bar.innerHTML = `
        <div class="ia-context-main"><strong data-ia-context-count>0 selected</strong><span data-ia-context-scope>Current table</span></div>
        <div class="ia-context-actions" data-ia-context-actions></div>
        <button type="button" class="ia-context-clear" data-ia-context-clear>Clear</button>`;
    document.body.appendChild(bar);
    bar.addEventListener('click', (event) => {
        if (event.target.closest('[data-ia-context-clear]')) {
            document.querySelectorAll('table.ia-table tbody input[type="checkbox"]:checked').forEach((checkbox) => {
                checkbox.checked = false;
                checkbox.dispatchEvent(new Event('change', { bubbles: true }));
            });
            updateContextualActionBar();
        }
        const proxy = event.target.closest('[data-ia-proxy-action]');
        if (proxy) {
            const target = document.getElementById(proxy.dataset.iaProxyAction);
            target?.click();
        }
    });
    return bar;
}

function updateContextualActionBar() {
    const bar = ensureContextualActionBar();
    const selected = Array.from(document.querySelectorAll('table.ia-table tbody input[type="checkbox"]:checked'))
        .filter((checkbox) => checkbox.offsetParent !== null);
    if (!selected.length) {
        bar.hidden = true;
        document.body.classList.remove('ia-has-selection');
        return;
    }
    const table = selected[0].closest('table');
    const tableLabel = table ? tableTitle(table) : 'Current table';
    bar.hidden = false;
    document.body.classList.add('ia-has-selection');
    bar.querySelector('[data-ia-context-count]').textContent = `${selected.length.toLocaleString()} selected`;
    bar.querySelector('[data-ia-context-scope]').textContent = tableLabel;

    const actionHost = bar.querySelector('[data-ia-context-actions]');
    const actionIds = ['bulkExportBtn', 'bulkUpdateBtn', 'bulkDeleteBtn', 'bulkAnalyzeBtn', 'bulkMoveBtn'];
    const actions = actionIds
        .map((id) => document.getElementById(id))
        .filter((button) => button && !button.disabled && button.offsetParent !== null)
        .slice(0, 4);
    actionHost.innerHTML = actions.map((button) => `
        <button type="button" class="ia-context-action" data-ia-proxy-action="${escapeAttr(button.id)}">
            ${escapeHtml(textOf(button) || 'Action')}
        </button>`).join('');
}

function setupGlobalSelectionContext() {
    if (document.body.dataset.iaSelectionContextSetup === 'true') return;
    document.addEventListener('change', (event) => {
        if (event.target.matches?.('table.ia-table tbody input[type="checkbox"], table.ia-table thead input[type="checkbox"]')) {
            window.setTimeout(updateContextualActionBar, 20);
        }
    });
    document.body.dataset.iaSelectionContextSetup = 'true';
}

function enhanceScrollPolicy(root = document) {
    queryWithin(root, SELECTOR.controlSurfaces).forEach((surface) => {
        if (!(surface instanceof HTMLElement)) return;
        if (surface.matches('[data-ia-sticky="false"], [data-ia-role="inline-controls"]')) return;
        if (surface.closest('[data-ia-sticky="false"], .ia-data-scroll-region, .ia-table-scroll, .table-wrapper, .table-responsive')) return;
        surface.classList.add('ia-fixed-control-surface');
    });

    queryWithin(root, SELECTOR.dataRegions).forEach((region) => {
        if (!(region instanceof HTMLElement)) return;
        if (region.matches('[data-ia-scroll="false"], [data-ia-role="controls"], [data-ia-sticky="true"]')) return;
        if (region.closest('[data-ia-scroll="false"]')) return;
        region.classList.add('ia-data-scroll-region');
        if (!region.getAttribute('role') && region.querySelector('table, .file-card, .file-row-item, .explorer-item, .result-card, .search-result-item')) {
            region.setAttribute('role', 'region');
        }
        if (!region.getAttribute('aria-label')) {
            const heading = region.closest('.section, .section-card, .stat-card, .card, .results-section, .search-results-section')?.querySelector('h1,h2,h3,h4,h5,h6,.section-label');
            if (heading) region.setAttribute('aria-label', textOf(heading));
        }
    });

    queryWithin(root, '.results-section, .search-results-section').forEach((section) => {
        if (!(section instanceof HTMLElement)) return;
        if (section.matches('[data-ia-scroll="false"]')) return;
        section.classList.add('ia-scroll-framed-section');
        Array.from(section.children).forEach((child) => {
            if (!(child instanceof HTMLElement)) return;
            if (child.matches('script, style, [data-ia-sticky="false"], [data-ia-role="inline-controls"]')) return;
            if (child.matches('.results-header, .section-header, .filter-actions, .filter-actions-bar, .results-actions, .results-sort, .results-pagination, [data-ia-role="controls"], [data-ia-sticky="true"]')) {
                child.classList.add('ia-fixed-control-row');
            } else if (!child.matches('[data-ia-scroll="false"]')) {
                child.classList.add('ia-data-scroll-region');
            }
        });
    });
}

function refresh(root = document) {
    enhanceExistingFilters(root);
    enhanceScrollPolicy(root);
    enhanceTables(root);
    enhanceModals(root);
    injectCommandTrigger();
    updateContextualActionBar();
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
    initializeWorkspaceShell();
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
    applyDensity,
    applyWorkspaceTheme,
    openCommandPalette,
    resetWorkspacePreferences,
    version: '2026.09.16-enterprise'
});

export { refresh, setButtonBusy, highlightNewRecord, applyDensity, applyWorkspaceTheme, openCommandPalette };
