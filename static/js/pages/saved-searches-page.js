/**
 * Saved Searches Page JavaScript
 * Enhances the server-rendered saved-search workbench without inline handlers.
 * Uses the real saved-search API (PUT/DELETE /api/search/saved/<id>).
 */

let translations = {};
let initialized = false;

function t(key, fallback) {
    return translations[key] || fallback || key;
}

function parsePageData() {
    const pageDataEl = document.getElementById('saved-searches-page-data');
    if (!pageDataEl) return;

    try {
        const data = JSON.parse(pageDataEl.textContent || '{}');
        translations = data.translations || {};
        window.translations = window.translations || {};
        Object.assign(window.translations, translations);
    } catch (error) {
        console.error('Error parsing saved searches page data:', error);
    }
}

function getCSRFToken() {
    const metaTag = document.querySelector('meta[name="csrf-token"]');
    return metaTag ? metaTag.getAttribute('content') : '';
}

function notify(type, message) {
    if (type === 'success' && window.showSuccess) {
        window.showSuccess(message);
        return;
    }
    if (type === 'error' && window.showError) {
        window.showError(message);
        return;
    }
    if (window.MessageSystem) {
        window.MessageSystem.show(message, type === 'error' ? 'error' : 'success');
        return;
    }
    console[type === 'error' ? 'error' : 'log'](message);
}

async function confirmAction(message) {
    if (window.showConfirm) {
        return window.showConfirm(message, {
            title: t('deleteSavedSearch', 'Delete saved search'),
            confirmText: t('delete', 'Delete'),
            cancelText: t('cancel', 'Cancel'),
            variant: 'danger'
        });
    }
    return window.confirm(message);
}

function savedSearchCards() {
    return Array.from(document.querySelectorAll('.saved-search-item'));
}

function updateVisibleCount() {
    const visible = savedSearchCards().filter(card => !card.hidden).length;
    const total = savedSearchCards().length;
    const visibleEl = document.getElementById('savedSearchVisibleCount');
    const totalEl = document.getElementById('savedSearchTotalCount');
    if (visibleEl) visibleEl.textContent = String(visible);
    if (totalEl) totalEl.textContent = String(total);

    const emptyState = document.getElementById('savedSearchEmptyState');
    if (emptyState) {
        emptyState.hidden = total !== 0;
    }

    const noMatches = document.getElementById('savedSearchNoMatches');
    if (noMatches) {
        const hasFilter = !!(document.getElementById('searchSaved')?.value || '').trim();
        noMatches.hidden = !(hasFilter && total > 0 && visible === 0);
    }
}

// Client-side filter by saved-search name.
function filterSavedSearches() {
    const searchTerm = (document.getElementById('searchSaved')?.value || '').toLowerCase().trim();
    savedSearchCards().forEach(card => {
        const name = card.dataset.name || '';
        card.hidden = !!searchTerm && !name.includes(searchTerm);
    });
    updateVisibleCount();
}

function updateCardName(card, newName) {
    if (!card) return;
    card.dataset.name = newName.toLowerCase();
    const title = card.querySelector('.saved-search-name-text');
    if (title) title.textContent = newName;
    const renameButton = card.querySelector('[data-saved-search-rename]');
    if (renameButton) renameButton.dataset.searchName = newName;
}

// Rename a saved search (Edit action).
async function renameSavedSearch(searchId, currentName, trigger = null) {
    const newName = window.prompt(t('renamePrompt', 'Enter a new name for this search:'), currentName);
    if (newName === null) return;

    const trimmed = String(newName || '').trim();
    if (!trimmed || trimmed === currentName) return;

    try {
        window.InforaxisDataInterface?.setButtonBusy?.(trigger, true, { label: t('renaming', 'Renaming') });
        const response = await fetch(`/api/search/saved/${searchId}`, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCSRFToken()
            },
            body: JSON.stringify({ name: trimmed })
        });

        if (!response.ok) {
            const err = await response.json().catch(() => ({}));
            throw new Error(err.error || t('unknownError', 'Unknown error'));
        }

        const card = document.querySelector(`.saved-search-item[data-search-id="${String(searchId).replace(/"/g, '\\"')}"]`);
        updateCardName(card, trimmed);
        filterSavedSearches();
        notify('success', t('searchUpdatedSuccessfully', 'Search updated successfully'));
    } catch (error) {
        notify('error', `${t('error', 'Error')}: ${error.message}`);
    } finally {
        window.InforaxisDataInterface?.setButtonBusy?.(trigger, false);
    }
}

// Delete a saved search.
async function deleteSavedSearch(searchId, trigger = null) {
    const confirmed = await confirmAction(t('deleteSearchConfirm', 'Are you sure you want to delete this saved search?'));
    if (!confirmed) return;

    try {
        window.InforaxisDataInterface?.setButtonBusy?.(trigger, true, { label: t('deleting', 'Deleting') });
        const response = await fetch(`/api/search/saved/${searchId}`, {
            method: 'DELETE',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCSRFToken()
            }
        });

        if (!response.ok) {
            const err = await response.json().catch(() => ({}));
            throw new Error(err.error || t('unknownError', 'Unknown error'));
        }

        const card = document.querySelector(`.saved-search-item[data-search-id="${String(searchId).replace(/"/g, '\\"')}"]`);
        if (card) card.remove();
        updateVisibleCount();
        notify('success', t('searchDeletedSuccessfully', 'Search deleted successfully'));
    } catch (error) {
        notify('error', `${t('error', 'Error')}: ${error.message}`);
    } finally {
        window.InforaxisDataInterface?.setButtonBusy?.(trigger, false);
    }
}

function bindEvents() {
    const filterInput = document.getElementById('searchSaved');
    if (filterInput) {
        filterInput.addEventListener('input', filterSavedSearches);
    }

    const container = document.getElementById('savedSearchesContainer');
    if (container) {
        container.addEventListener('click', (event) => {
            const renameButton = event.target.closest('[data-saved-search-rename]');
            if (renameButton) {
                event.preventDefault();
                renameSavedSearch(renameButton.dataset.searchId, renameButton.dataset.searchName || '', renameButton);
                return;
            }

            const deleteButton = event.target.closest('[data-saved-search-delete]');
            if (deleteButton) {
                event.preventDefault();
                deleteSavedSearch(deleteButton.dataset.searchId, deleteButton);
            }
        });
    }
}

function initializeSavedSearchesPage() {
    if (initialized) return;
    initialized = true;
    parsePageData();
    bindEvents();
    updateVisibleCount();
    console.log('Saved searches page loaded');
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initializeSavedSearchesPage, { once: true });
} else {
    initializeSavedSearchesPage();
}

// Legacy globals retained for older callers/bookmarks/tests.
window.filterSavedSearches = filterSavedSearches;
window.renameSavedSearch = renameSavedSearch;
window.deleteSavedSearch = deleteSavedSearch;

export default function init() {
    initializeSavedSearchesPage();
}
