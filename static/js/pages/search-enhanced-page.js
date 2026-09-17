/**
 * Search Enhanced Page JavaScript
 * Extracted from search_enhanced.html
 * Enhanced with advanced search features
 */

import { initializeSearch, loadSearchHistory, loadSavedSearches } from '../modules/search/global-search.js';
import advancedSearch from '../modules/search/advanced-search.js';

let initialized = false;

async function initializeEnhancedSearchPage() {
    if (initialized) {
        console.debug('Enhanced search page already initialized, skipping duplicate setup');
        return;
    }
    initialized = true;

    initializeSearch();
    advancedSearch.initializeAdvancedSearch();
    loadSearchHistory();
    loadSavedSearches();
}

// Clear search history function
window.enhancedSearch = window.enhancedSearch || {};

window.enhancedSearch.clearHistory = async function() {
    const confirmMsg = window.appTranslations?.['Clear all search history?'] ||
                      'Clear all search history?';

    if (!confirm(confirmMsg)) return;

    try {
        const response = await fetch('/api/search/history', {
            method: 'DELETE',
            headers: {
                'X-CSRFToken': document.querySelector('meta[name="csrf-token"]')?.getAttribute('content') || ''
            }
        });

        if (response.ok) {
            const searchHistoryEl = document.getElementById('searchHistory');
            if (searchHistoryEl) {
                const noHistoryMsg = window.appTranslations?.['No search history'] || 'No search history';
                searchHistoryEl.innerHTML = `<p class="text-muted small">${noHistoryMsg}</p>`;
            }
        }
    } catch (error) {
        console.error('Error clearing history:', error);
        const errorMsg = window.appTranslations?.['Error clearing history'] || 'Error clearing history';
        alert(errorMsg);
    }
};

/**
 * Default initialization function for universal-initializer
 */
export default async function init() {
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initializeEnhancedSearchPage, { once: true });
    } else {
        await initializeEnhancedSearchPage();
    }
}

// Direct module fallback: search_enhanced.html includes this module explicitly,
// while the universal initializer skips explicit page modules to prevent double
// work. The guard above keeps dynamically imported usage safe as well.
init();
