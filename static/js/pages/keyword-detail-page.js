/**
 * Keyword Detail Page JavaScript
 * Handles record-level keyword actions without inline event handlers.
 */

let pageData = {};
let translations = {};
let initialized = false;

function readPageData() {
    const pageDataEl = document.getElementById('keyword-detail-page-data');
    if (!pageDataEl) return {};
    try {
        return JSON.parse(pageDataEl.textContent || '{}');
    } catch (error) {
        console.error('Error parsing keyword detail page data:', error);
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
            title: translations.deleteConfirm || 'Delete keyword',
            confirmLabel: translations.delete || 'Delete',
            type: 'danger'
        });
    }
    const originalConfirm = window.__originalConfirm || window.confirm;
    return originalConfirm(message);
}

async function deleteKeyword(id) {
    if (!(await confirmRecordDelete(translations.deleteConfirm || 'Are you sure you want to delete this keyword?'))) return;

    try {
        const response = await fetch(`/api/keywords/${id}`, {
            method: 'DELETE',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCSRFToken()
            }
        });
        const data = await response.json().catch(() => ({}));
        if (response.ok && data.success) {
            notify(translations.keywordDeletedSuccessfully || 'Keyword deleted successfully!', 'success');
            window.location.href = pageData.keywords_list_url || '/keywords';
            return;
        }
        notify(`${translations.error || 'Error'}: ${data.error || response.statusText}`, 'error');
    } catch (error) {
        notify(`${translations.error || 'Error'}: ${error.message}`, 'error');
    }
}

function initKeywordDetailPage() {
    if (initialized) return;
    initialized = true;
    pageData = readPageData();
    translations = pageData.translations || {};
    window.translations = window.translations || {};
    Object.assign(window.translations, translations);

    document.querySelectorAll('[data-keyword-delete]').forEach((button) => {
        button.addEventListener('click', () => deleteKeyword(button.dataset.keywordId));
    });
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initKeywordDetailPage);
} else {
    initKeywordDetailPage();
}

window.deleteKeyword = deleteKeyword;

export default function init() {
    initKeywordDetailPage();
}
