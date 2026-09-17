/**
 * Side Detail Page JavaScript
 * Handles record-level side actions without inline event handlers.
 */

let pageData = {};
let translations = {};
let initialized = false;

function readPageData() {
    const pageDataEl = document.getElementById('side-detail-page-data');
    if (!pageDataEl) return {};
    try {
        return JSON.parse(pageDataEl.textContent || '{}');
    } catch (error) {
        console.error('Error parsing side detail page data:', error);
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
            title: translations.deleteSideConfirm || 'Delete side',
            confirmLabel: translations.delete || 'Delete',
            type: 'danger'
        });
    }
    const originalConfirm = window.__originalConfirm || window.confirm;
    return originalConfirm(message);
}

async function deleteSide(id, sideName = '') {
    const confirmMessage = sideName
        ? `${translations.deleteSideConfirm || 'Are you sure you want to delete this side?'} ${sideName}`
        : translations.deleteSideConfirm;
    if (!(await confirmRecordDelete(confirmMessage))) return;

    try {
        const response = await fetch(`/api/sides/${id}`, {
            method: 'DELETE',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCSRFToken()
            }
        });
        const data = await response.json().catch(() => ({}));
        if (response.ok && data.success) {
            notify(translations.sideDeletedSuccessfully || 'Side deleted successfully!', 'success');
            window.setTimeout(() => {
                window.location.href = pageData.sides_list_url || '/sides';
            }, 300);
            return;
        }
        notify(`${translations.error || 'Error'}: ${data.error || response.statusText}`, 'error');
    } catch (error) {
        notify(`${translations.error || 'Error'}: ${error.message}`, 'error');
    }
}

function initSideDetailPage() {
    if (initialized) return;
    initialized = true;
    pageData = readPageData();
    translations = pageData.translations || {};
    window.translations = window.translations || {};
    Object.assign(window.translations, translations);

    document.querySelectorAll('[data-side-delete]').forEach((button) => {
        button.addEventListener('click', () => {
            deleteSide(button.dataset.sideId, button.dataset.sideName || '');
        });
    });
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initSideDetailPage);
} else {
    initSideDetailPage();
}

window.deleteSide = deleteSide;

export default function init() {
    initSideDetailPage();
}
