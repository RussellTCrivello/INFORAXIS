/**
 * Source Detail Page JavaScript
 * Handles record-level source actions without inline event handlers.
 */

let pageData = {};
let translations = {};
let initialized = false;

function readPageData() {
    const pageDataEl = document.getElementById('source-detail-page-data');
    if (!pageDataEl) return {};
    try {
        return JSON.parse(pageDataEl.textContent || '{}');
    } catch (error) {
        console.error('Error parsing source detail page data:', error);
        return {};
    }
}

function getCSRFToken() {
    const metaTag = document.querySelector('meta[name="csrf-token"]');
    return metaTag ? metaTag.getAttribute('content') : '';
}

function notify(message, type = 'error') {
    if (type === 'success' && window.showSuccess) {
        window.showSuccess(message);
        return;
    }
    if (type === 'error' && window.showError) {
        window.showError(message);
        return;
    }
    console[type === 'error' ? 'error' : 'log'](message);
}

async function confirmRecordDelete(message) {
    if (window.showConfirm) {
        return window.showConfirm(message, {
            title: translations.deleteSourceConfirm || 'Delete source',
            confirmLabel: translations.delete || 'Delete',
            type: 'danger'
        });
    }
    const originalConfirm = window.__originalConfirm || window.confirm;
    return originalConfirm(message);
}

async function deleteSource(id, sourceName = '') {
    const confirmMessage = sourceName
        ? `${translations.deleteSourceConfirm || 'Are you sure you want to delete this source?'} ${sourceName}`
        : translations.deleteSourceConfirm;
    if (!(await confirmRecordDelete(confirmMessage))) return;

    try {
        const response = await fetch(`/api/sources/${id}`, {
            method: 'DELETE',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCSRFToken()
            }
        });
        const data = await response.json().catch(() => ({}));
        if (response.ok && data.success) {
            notify(translations.sourceDeletedSuccessfully || 'Source deleted successfully!', 'success');
            window.setTimeout(() => {
                window.location.href = pageData.sources_list_url || '/sources';
            }, 300);
            return;
        }
        notify(`${translations.error || 'Error'}: ${data.error || response.statusText}`, 'error');
    } catch (error) {
        notify(`${translations.error || 'Error'}: ${error.message}`, 'error');
    }
}

function initSourceDetailPage() {
    if (initialized) return;
    initialized = true;
    pageData = readPageData();
    translations = pageData.translations || {};
    window.translations = window.translations || {};
    Object.assign(window.translations, translations);

    document.querySelectorAll('[data-source-delete]').forEach((button) => {
        button.addEventListener('click', () => {
            deleteSource(button.dataset.sourceId, button.dataset.sourceName || '');
        });
    });
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initSourceDetailPage);
} else {
    initSourceDetailPage();
}

window.deleteSource = deleteSource;

export default function init() {
    initSourceDetailPage();
}
