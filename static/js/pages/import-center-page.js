/**
 * Import Center workspace behavior.
 * Extracted from the template so preview, validation, and job launch states can
 * share the enterprise workbench styling and stable control/data-region model.
 */

const IMPORT_LABELS_ID = 'import-center-labels';

let labels = {};
let pendingImport = null;

function readLabels() {
    const node = document.getElementById(IMPORT_LABELS_ID);
    if (!node) return {};
    try {
        return JSON.parse(node.textContent || '{}');
    } catch (error) {
        console.warn('Import Center labels could not be parsed', error);
        return {};
    }
}

function t(key, fallback) {
    return labels[key] || fallback;
}

function csrfToken() {
    return document.querySelector('meta[name="csrf-token"]')?.getAttribute('content') || '';
}

function valueOf(id) {
    return document.getElementById(id)?.value.trim() || '';
}

function selectOption(value, label) {
    const option = document.createElement('option');
    option.value = value;
    option.textContent = label;
    return option;
}

function fillSelect(id, rows) {
    const select = document.getElementById(id);
    if (!select) return;
    const fragment = document.createDocumentFragment();
    fragment.append(selectOption('', t('select', '-- select --')));
    rows.forEach((row) => {
        const name = row?.name || '';
        if (name) fragment.append(selectOption(name, name));
    });
    select.replaceChildren(fragment);
}

async function fetchJson(url, options = {}) {
    const response = await fetch(url, options);
    let data = null;
    try {
        data = await response.json();
    } catch (error) {
        data = null;
    }
    if (!response.ok) {
        const message = data?.error?.message || response.statusText || t('networkError', 'Import service could not be reached.');
        throw new Error(message);
    }
    return data || {};
}

async function loadSelects() {
    try {
        const [sources, sides] = await Promise.all([
            fetchJson('/api/input/sources', { headers: { Accept: 'application/json' } }),
            fetchJson('/api/input/sides', { headers: { Accept: 'application/json' } })
        ]);
        fillSelect('biSource', sources.sources || []);
        fillSelect('biSide', sides.sides || []);
    } catch (error) {
        showMessage(error.message || t('networkError', 'Import service could not be reached.'), false);
    }
}

function humanizeKey(key) {
    return String(key).replace(/_/g, ' ');
}

function previewValue(value) {
    if (value === null || value === undefined) return '';
    if (typeof value === 'number') return Number.isInteger(value) ? value.toLocaleString() : value.toLocaleString(undefined, { maximumFractionDigits: 2 });
    if (typeof value === 'boolean') return value ? 'true' : 'false';
    return String(value);
}

function showPreview(preview = {}, pending = null) {
    const box = document.getElementById('previewBox');
    const confirmRow = document.getElementById('confirmRow');
    if (!box || !confirmRow) return;

    pendingImport = pending;
    const entries = Object.entries(preview).filter(([_key, value]) => value !== null && value !== undefined && typeof value !== 'object');
    const fragment = document.createDocumentFragment();

    if (entries.length) {
        const list = document.createElement('dl');
        list.className = 'import-preview-list';
        entries.forEach(([key, value]) => {
            const row = document.createElement('div');
            row.className = 'import-preview-row';
            const term = document.createElement('dt');
            term.textContent = humanizeKey(key);
            const description = document.createElement('dd');
            description.textContent = previewValue(value);
            row.append(term, description);
            list.append(row);
        });
        fragment.append(list);
    }

    const note = document.createElement('div');
    note.className = 'import-preview-note';
    const icon = document.createElement('i');
    icon.className = 'bi bi-info-circle';
    icon.setAttribute('aria-hidden', 'true');
    const text = document.createElement('span');
    text.textContent = t('review', 'Review carefully. Imports run as jobs with full error reporting.');
    note.append(icon, text);
    fragment.append(note);

    box.replaceChildren(fragment);
    confirmRow.classList.toggle('d-none', !pendingImport);
}

function showMessage(text, ok) {
    const target = document.getElementById('importMsg');
    if (!target) return;
    const alert = document.createElement('div');
    alert.className = `alert ${ok ? 'alert-success' : 'alert-danger'}`;
    alert.setAttribute('role', 'alert');
    alert.textContent = text;
    target.replaceChildren(alert);
}

async function postJson(url, body) {
    return fetchJson(url, {
        method: 'POST',
        headers: {
            Accept: 'application/json',
            'Content-Type': 'application/json',
            'X-CSRFToken': csrfToken()
        },
        body: JSON.stringify(body)
    });
}

function pathList() {
    return (document.getElementById('biPaths')?.value || '')
        .split('\n')
        .map((path) => path.trim())
        .filter(Boolean);
}

async function validateDomainImport() {
    try {
        const data = await postJson('/api/import/validate', { type: 'domain_import', data_file: valueOf('diFile') || null });
        if (data.success) showPreview({ ...(data.preview || {}), note: t('validated', 'validated') }, null);
        else showMessage(data.error?.message || t('validationFailed', 'Validation failed'), false);
    } catch (error) {
        showMessage(error.message || t('validationFailed', 'Validation failed'), false);
    }
}

async function previewDomainImport() {
    try {
        const body = { type: 'domain_import', data_file: valueOf('diFile') || null };
        const data = await postJson('/api/import/preview', body);
        if (data.success) {
            showPreview(data.stats || data.job?.statistics || { status: data.job?.status, note: t('dryRunCompleted', 'dry run job completed') }, body);
        } else {
            showMessage(data.error?.message || t('previewFailed', 'Preview failed'), false);
        }
    } catch (error) {
        showMessage(error.message || t('previewFailed', 'Preview failed'), false);
    }
}

async function stageBackup(url, successMessage, fallbackError) {
    try {
        const file = document.getElementById('buFile')?.files?.[0];
        if (!file) {
            showMessage(t('chooseBackup', 'Choose a backup file first.'), false);
            return;
        }
        const formData = new FormData();
        formData.append('file', file);
        const data = await fetchJson(url, {
            method: 'POST',
            headers: { 'X-CSRFToken': csrfToken() },
            body: formData
        });
        if (data.success && data.job?.job_id) {
            if (successMessage) showMessage(successMessage, true);
            window.location = `/operations/jobs/${data.job.job_id}`;
        } else {
            showMessage(data.error?.message || fallbackError, false);
        }
    } catch (error) {
        showMessage(error.message || fallbackError, false);
    }
}

async function validateBatchImport() {
    try {
        const body = { type: 'batch_import', file_paths: pathList() };
        const data = await postJson('/api/import/validate', body);
        if (data.success) showPreview(data.preview || {}, { ...body, source: valueOf('biSource'), side: valueOf('biSide') });
        else showMessage(data.error?.message || t('validationFailed', 'Validation failed'), false);
    } catch (error) {
        showMessage(error.message || t('validationFailed', 'Validation failed'), false);
    }
}

function startBatchImport() {
    if (!valueOf('biSource') || !valueOf('biSide')) {
        showMessage(t('selectSourceSide', 'Select a source and a side.'), false);
        return;
    }
    startJob({ type: 'batch_import', file_paths: pathList(), source: valueOf('biSource'), side: valueOf('biSide') });
}

async function startJob(body) {
    try {
        const data = await postJson('/api/import/jobs', body);
        if (data.success && data.job?.job_id) window.location = `/operations/jobs/${data.job.job_id}`;
        else showMessage(data.error?.message || t('jobFailed', 'Import job could not be created.'), false);
    } catch (error) {
        showMessage(error.message || t('jobFailed', 'Import job could not be created.'), false);
    }
}

function clearPreview() {
    const box = document.getElementById('previewBox');
    const confirmRow = document.getElementById('confirmRow');
    pendingImport = null;
    confirmRow?.classList.add('d-none');
    if (!box) return;
    const empty = document.createElement('div');
    empty.className = 'import-empty-state';
    empty.textContent = t('cleared', 'Cleared.');
    box.replaceChildren(empty);
}

function bind(id, eventName, handler) {
    document.getElementById(id)?.addEventListener(eventName, handler);
}

function initImportCenter() {
    labels = readLabels();
    loadSelects();

    bind('diValidate', 'click', validateDomainImport);
    bind('diPreview', 'click', previewDomainImport);
    bind('diStart', 'click', () => startJob({ type: 'domain_import', data_file: valueOf('diFile') || null }));
    bind('buValidate', 'click', () => stageBackup('/api/import/jobs', t('backupStaged', 'Backup staged. Starting validation job…'), t('stagingFailed', 'Staging failed')));
    bind('buStart', 'click', () => stageBackup('/api/import/jobs?type=backup_import', '', t('restoreFailed', 'Restore job failed to start')));
    bind('biValidate', 'click', validateBatchImport);
    bind('biStart', 'click', startBatchImport);
    bind('btnConfirmStart', 'click', () => {
        if (!pendingImport) {
            showMessage(t('nothingToStart', 'Nothing to start - run a preview first.'), false);
            return;
        }
        startJob(pendingImport);
    });
    bind('btnClearPreview', 'click', clearPreview);
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initImportCenter);
} else {
    initImportCenter();
}
