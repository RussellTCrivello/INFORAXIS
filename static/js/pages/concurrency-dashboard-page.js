/**
 * Enterprise concurrency monitoring workspace.
 * Keeps controls/tabs stable while polling only the metric and row regions.
 */

const POLL_INTERVAL_MS = 5000;

const ENDPOINTS = {
    metrics: '/concurrency/api/metrics',
    threads: '/concurrency/api/threads',
    processes: '/concurrency/api/processes',
    asyncTasks: '/concurrency/api/async-tasks',
    pools: '/concurrency/api/pools'
};

const MANAGER_FIELDS = {
    thread: [
        ['active', 'active_threads'],
        ['total', 'total_threads'],
        ['completed', 'completed'],
        ['errors', 'errors'],
        ['paused', 'paused']
    ],
    process: [
        ['active', 'active_processes'],
        ['total', 'total_processes'],
        ['completed', 'completed'],
        ['errors', 'errors'],
        ['memory', 'total_memory_mb', formatMegabytes],
        ['avgCpu', 'avg_cpu_percent', formatPercent]
    ],
    async: [
        ['active', 'active_tasks'],
        ['total', 'total_tasks'],
        ['completed', 'completed'],
        ['errors', 'errors'],
        ['paused', 'paused'],
        ['totalRuntime', 'total_runtime', formatSeconds]
    ],
    pool: [
        ['totalPools', 'total_pools'],
        ['totalWorkers', 'total_workers'],
        ['completed', 'total_completed'],
        ['failed', 'total_failed'],
        ['pending', 'total_pending'],
        ['memory', 'total_memory_mb', formatMegabytes]
    ]
};

const TABLES = {
    threads: {
        bodyId: 'threads-tbody',
        tableId: 'threads-table',
        emptyId: 'threads-empty',
        rowKey: 'threads',
        columns: [
            ['id', (row) => row.id],
            ['name', (row) => row.name || label('unknown', 'Unknown')],
            ['state', (row) => row.state || label('unknown', 'unknown'), 'state'],
            ['priority', (row) => row.priority]
        ]
    },
    processes: {
        bodyId: 'processes-tbody',
        tableId: 'processes-table',
        emptyId: 'processes-empty',
        rowKey: 'processes',
        columns: [
            ['id', (row) => row.id],
            ['name', (row) => row.name || label('unknown', 'Unknown')],
            ['state', (row) => row.state || label('unknown', 'unknown'), 'state'],
            ['pid', (row) => row.pid],
            ['priority', (row) => row.priority]
        ]
    },
    asyncTasks: {
        bodyId: 'async-tasks-tbody',
        tableId: 'async-tasks-table',
        emptyId: 'async-tasks-empty',
        rowKey: 'tasks',
        columns: [
            ['id', (row) => row.id],
            ['name', (row) => row.name || label('unknown', 'Unknown')],
            ['state', (row) => row.state || label('unknown', 'unknown'), 'state'],
            ['priority', (row) => row.priority]
        ]
    },
    pools: {
        bodyId: 'pools-tbody',
        tableId: 'pools-table',
        emptyId: 'pools-empty',
        rowKey: 'pools',
        columns: [
            ['id', (row) => row.id],
            ['name', (row) => row.name || label('unknown', 'Unknown')],
            ['state', (row) => row.state || label('unknown', 'unknown'), 'state'],
            ['worker_count', (row) => row.worker_count || 0],
            ['active_workers', (row) => row.active_workers || 0],
            ['priority', (row) => row.priority]
        ]
    }
};

let labels = {};
let refreshInFlight = false;

function readLabels() {
    const node = document.getElementById('concurrency-labels');
    if (!node) return {};
    try {
        return JSON.parse(node.textContent || '{}');
    } catch (error) {
        console.warn('Concurrency labels could not be parsed', error);
        return {};
    }
}

function label(key, fallback) {
    return labels[key] || fallback;
}

function setLiveStatus(text, state = 'ready') {
    const status = document.getElementById('concurrencyLiveStatus');
    const textNode = document.getElementById('concurrencyLiveText');
    if (!status || !textNode) return;
    status.classList.toggle('is-refreshing', state === 'refreshing');
    status.classList.toggle('is-error', state === 'error');
    textNode.textContent = text;
}

async function fetchJson(url) {
    const response = await fetch(url, { headers: { Accept: 'application/json' } });
    if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
    return response.json();
}

function formatValue(value) {
    if (value === null || value === undefined || value === '') return label('notAvailable', 'N/A');
    if (typeof value === 'number') return Number.isInteger(value) ? value.toLocaleString() : value.toLocaleString(undefined, { maximumFractionDigits: 2 });
    return String(value);
}

function formatMegabytes(value) {
    if (value === null || value === undefined) return label('notAvailable', 'N/A');
    return `${Number(value).toLocaleString(undefined, { maximumFractionDigits: 2 })} MB`;
}

function formatPercent(value) {
    if (value === null || value === undefined) return label('notAvailable', 'N/A');
    return `${Number(value).toLocaleString(undefined, { maximumFractionDigits: 1 })}%`;
}

function formatSeconds(value) {
    if (value === null || value === undefined) return label('notAvailable', 'N/A');
    return `${Number(value).toLocaleString(undefined, { maximumFractionDigits: 2 })}s`;
}

function createMetricRow(labelText, value) {
    const row = document.createElement('div');
    row.className = 'concurrency-metric-row';

    const labelEl = document.createElement('span');
    labelEl.textContent = labelText;

    const valueEl = document.createElement('strong');
    valueEl.textContent = formatValue(value);

    row.append(labelEl, valueEl);
    return row;
}

function createStateRow(status) {
    const row = document.createElement('div');
    row.className = 'concurrency-state-row';

    const labelEl = document.createElement('span');
    labelEl.textContent = label('status', 'Status');

    const valueEl = document.createElement('strong');
    valueEl.className = 'concurrency-state-value';

    const dot = document.createElement('span');
    dot.className = 'concurrency-status-dot';
    dot.dataset.status = String(status || 'unknown').toLowerCase();

    const text = document.createElement('span');
    text.textContent = status || label('unknown', 'unknown');

    valueEl.append(dot, text);
    row.append(labelEl, valueEl);
    return row;
}

function renderManager(type, metrics = {}) {
    const container = document.getElementById(`${type}-metrics`);
    if (!container) return;

    const fragment = document.createDocumentFragment();
    if (metrics.status === 'error') {
        const error = document.createElement('div');
        error.className = 'concurrency-error';
        error.textContent = `${label('error', 'Error')}: ${metrics.error || label('unknown', 'unknown')}`;
        fragment.append(error);
        container.replaceChildren(fragment);
        return;
    }

    fragment.append(createStateRow(metrics.status || label('unknown', 'unknown')));
    (MANAGER_FIELDS[type] || []).forEach(([labelKey, metricKey, formatter]) => {
        const value = metrics[metricKey];
        if (value === null || value === undefined || value === '') return;
        fragment.append(createMetricRow(label(labelKey, labelKey), formatter ? formatter(value) : value));
    });

    if (!fragment.childNodes.length) {
        const empty = document.createElement('div');
        empty.className = 'concurrency-empty';
        empty.textContent = label('notAvailable', 'N/A');
        fragment.append(empty);
    }

    container.replaceChildren(fragment);
}

function createStateCell(value) {
    const pill = document.createElement('span');
    pill.className = 'concurrency-state-pill';

    const dot = document.createElement('span');
    dot.className = 'concurrency-status-dot';
    dot.dataset.status = String(value || 'unknown').toLowerCase();

    const text = document.createElement('span');
    text.textContent = value || label('unknown', 'unknown');

    pill.append(dot, text);
    return pill;
}

function renderRows(config, rows) {
    const tbody = document.getElementById(config.bodyId);
    const table = document.getElementById(config.tableId);
    const empty = document.getElementById(config.emptyId);
    if (!tbody || !table || !empty) return;

    const hasRows = Array.isArray(rows) && rows.length > 0;
    table.classList.toggle('d-none', !hasRows);
    empty.classList.toggle('d-none', hasRows);

    if (!hasRows) {
        tbody.replaceChildren();
        return;
    }

    const fragment = document.createDocumentFragment();
    rows.forEach((row) => {
        const tr = document.createElement('tr');
        config.columns.forEach(([_key, getter, type]) => {
            const td = document.createElement('td');
            const value = getter(row);
            if (type === 'state') {
                td.append(createStateCell(value));
            } else {
                td.textContent = formatValue(value);
            }
            tr.append(td);
        });
        fragment.append(tr);
    });
    tbody.replaceChildren(fragment);
    window.INFORAXISResponsive?.annotateResponsiveTables?.(table);
}

function renderTableError(config, error) {
    const tbody = document.getElementById(config.bodyId);
    const table = document.getElementById(config.tableId);
    const empty = document.getElementById(config.emptyId);
    if (!tbody || !table || !empty) return;

    if (!empty.dataset.defaultText) empty.dataset.defaultText = empty.textContent;
    table.classList.add('d-none');
    empty.classList.remove('d-none');
    empty.classList.add('concurrency-error');
    empty.textContent = `${label('error', 'Error')}: ${error.message || error}`;
    tbody.replaceChildren();
}

function resetEmptyState(config) {
    const empty = document.getElementById(config.emptyId);
    if (!empty) return;
    if (!empty.dataset.defaultText) empty.dataset.defaultText = empty.textContent;
    empty.classList.remove('concurrency-error');
    empty.textContent = empty.dataset.defaultText;
}

function handleMetricsResponse(data) {
    if (!data || !data.success) return;
    renderManager('thread', data.metrics?.thread_manager || {});
    renderManager('process', data.metrics?.process_manager || {});
    renderManager('async', data.metrics?.async_manager || {});
    renderManager('pool', data.metrics?.pool_manager || {});
}

function handleRowsResponse(config, data) {
    resetEmptyState(config);
    if (!data || !data.success) {
        renderRows(config, []);
        return;
    }
    renderRows(config, data[config.rowKey] || []);
}

async function refreshMetrics() {
    if (refreshInFlight) return;
    refreshInFlight = true;
    setLiveStatus(label('refreshing', 'Refreshing...'), 'refreshing');

    const results = await Promise.allSettled([
        fetchJson(ENDPOINTS.metrics),
        fetchJson(ENDPOINTS.threads),
        fetchJson(ENDPOINTS.processes),
        fetchJson(ENDPOINTS.asyncTasks),
        fetchJson(ENDPOINTS.pools)
    ]);

    try {
        if (results[0].status === 'fulfilled') {
            handleMetricsResponse(results[0].value);
        } else {
            ['thread', 'process', 'async', 'pool'].forEach((type) => renderManager(type, { status: 'error', error: results[0].reason.message }));
        }

        const tableOrder = [TABLES.threads, TABLES.processes, TABLES.asyncTasks, TABLES.pools];
        tableOrder.forEach((config, index) => {
            const result = results[index + 1];
            if (result.status === 'fulfilled') handleRowsResponse(config, result.value);
            else renderTableError(config, result.reason);
        });

        const hasError = results.some((result) => result.status === 'rejected');
        const timestamp = new Intl.DateTimeFormat(undefined, { hour: '2-digit', minute: '2-digit', second: '2-digit' }).format(new Date());
        setLiveStatus(hasError ? label('refreshFailed', 'Refresh failed') : `${label('updated', 'Updated')} ${timestamp}`, hasError ? 'error' : 'ready');
    } finally {
        refreshInFlight = false;
    }
}

function initConcurrencyDashboard() {
    labels = readLabels();
    const refreshButton = document.getElementById('refreshConcurrency');
    refreshButton?.addEventListener('click', () => refreshMetrics());

    refreshMetrics();
    setInterval(() => {
        if (!document.hidden) refreshMetrics();
    }, POLL_INTERVAL_MS);
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initConcurrencyDashboard);
} else {
    initConcurrencyDashboard();
}

export default function init() {
    return Promise.resolve();
}
