/**
 * Search Enhanced Page JavaScript
 * Extracted from search_enhanced.html
 * Enhanced with advanced search features
 */

import { initializeSearch, loadSearchHistory, loadSavedSearches } from '../modules/search/global-search.js';
import advancedSearch from '../modules/search/advanced-search.js';

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
    initializeSearch();
    advancedSearch.initializeAdvancedSearch();
    loadSearchHistory();
    loadSavedSearches();
}

// Initialize advanced search when page loads (fallback for direct access)
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function() {
        initializeSearch();
        advancedSearch.initializeAdvancedSearch();
        loadSearchHistory();
        loadSavedSearches();
    });
} else {
    initializeSearch();
    advancedSearch.initializeAdvancedSearch();
    loadSearchHistory();
    loadSavedSearches();
}

