/**
 * Advanced Search Module
 * Google-like search with autocomplete, BM25, query expansion, fuzzy matching
 */

import { apiGet, apiPost } from '../api/api-client.js';
import { endpoints } from '../api/endpoints.js';
import { escapeHtml } from '../core/utils.js';
import notificationSystem from '../ui/notifications.js';

// Autocomplete state
let autocompleteTimeout = null;
let autocompleteController = null;
let currentSuggestions = [];
let selectedSuggestionIndex = -1;

/**
 * Initialize advanced search features
 */
export function initializeAdvancedSearch() {
    const searchInput = document.getElementById('searchQuery');
    if (!searchInput) return;

    // Create autocomplete container
    createAutocompleteContainer();

    // Setup autocomplete
    setupAutocomplete(searchInput);

    // Add advanced search options UI
    addAdvancedSearchOptions();

    // Handle keyboard navigation
    setupKeyboardNavigation(searchInput);
}

/**
 * Create autocomplete dropdown container
 */
function createAutocompleteContainer() {
    const searchInput = document.getElementById('searchQuery');
    if (!searchInput) return;

    // Check if container already exists
    if (document.getElementById('autocompleteContainer')) return;

    const container = document.createElement('div');
    container.id = 'autocompleteContainer';
    container.className = 'autocomplete-container position-relative';
    
    const dropdown = document.createElement('div');
    dropdown.id = 'autocompleteDropdown';
    dropdown.className = 'autocomplete-dropdown list-group position-absolute w-100';
    dropdown.style.display = 'none';
    dropdown.setAttribute('role', 'listbox');
    
    container.appendChild(dropdown);
    
    // Insert after search input
    const parent = searchInput.parentElement;
    parent.appendChild(container);
    

}

/**
 * Setup autocomplete functionality
 */
function setupAutocomplete(searchInput) {
    if (!searchInput) return;

    // Debounced input handler
    searchInput.addEventListener('input', function() {
        const query = this.value.trim();
        
        // Clear previous timeout
        if (autocompleteTimeout) {
            clearTimeout(autocompleteTimeout);
        }
        
        // Cancel previous request
        if (autocompleteController) {
            autocompleteController.abort();
        }

        // Hide dropdown if query is too short
        if (query.length < 2) {
            hideAutocomplete();
            return;
        }

        // Show autocomplete after delay
        autocompleteTimeout = setTimeout(() => {
            fetchAutocompleteSuggestions(query);
        }, 200);
    });

    // Hide autocomplete when clicking outside
    document.addEventListener('click', function(e) {
        const container = document.getElementById('autocompleteContainer');
        if (container && !container.contains(e.target) && e.target !== searchInput) {
            hideAutocomplete();
        }
    });

    // Handle input focus
    searchInput.addEventListener('focus', function() {
        const query = this.value.trim();
        if (query.length >= 2 && currentSuggestions.length > 0) {
            showAutocomplete(currentSuggestions);
        }
    });
}

/**
 * Fetch autocomplete suggestions
 */
async function fetchAutocompleteSuggestions(query) {
    if (!query || query.length < 2) return;

    try {
        // Cancel previous request
        if (autocompleteController) {
            autocompleteController.abort();
        }

        // Create new AbortController
        autocompleteController = new AbortController();
        const signal = autocompleteController.signal;

        const url = `/api/search/autocomplete?query=${encodeURIComponent(query)}&limit=10`;
        const response = await fetch(url, { signal });
        
        if (!response.ok) throw new Error('Autocomplete request failed');
        
        const data = await response.json();
        currentSuggestions = data.suggestions || [];
        
        // Show suggestions
        showAutocomplete(currentSuggestions);
        
    } catch (error) {
        if (error.name === 'AbortError') {
            return; // Request was cancelled
        }
        console.error('Autocomplete error:', error);
        // Don't show error to user for autocomplete failures
    }
}

/**
 * Show autocomplete dropdown
 */
function showAutocomplete(suggestions) {
    const dropdown = document.getElementById('autocompleteDropdown');
    if (!dropdown) return;

    if (!suggestions || suggestions.length === 0) {
        hideAutocomplete();
        return;
    }

    // Build HTML
    let html = '';
    suggestions.forEach((suggestion, index) => {
        const highlightedText = highlightQuery(suggestion.text, document.getElementById('searchQuery')?.value || '');
        const typeIcon = getTypeIcon(suggestion.type);
        const typeLabel = getTypeLabel(suggestion.type);
        
        html += `
            <div class="autocomplete-item list-group-item list-group-item-action" 
                 data-index="${index}" 
                 data-value="${escapeHtml(suggestion.text)}"
                 role="option"
                 tabindex="0">
                <div class="d-flex justify-content-between align-items-center">
                    <div class="flex-grow-1">
                        <i class="${typeIcon} me-2"></i>
                        ${highlightedText}
                        <span class="autocomplete-item-type">${typeLabel}</span>
                    </div>
                    ${suggestion.count > 0 ? `<span class="autocomplete-item-count">${suggestion.count}</span>` : ''}
                </div>
            </div>
        `;
    });

    dropdown.innerHTML = html;
    dropdown.style.display = 'block';
    selectedSuggestionIndex = -1;

    // Add click handlers
    dropdown.querySelectorAll('.autocomplete-item').forEach(item => {
        item.addEventListener('click', function() {
            selectSuggestion(this.dataset.value);
        });
    });
}

/**
 * Hide autocomplete dropdown
 */
function hideAutocomplete() {
    const dropdown = document.getElementById('autocompleteDropdown');
    if (dropdown) {
        dropdown.style.display = 'none';
    }
    selectedSuggestionIndex = -1;
}

/**
 * Select a suggestion
 */
function selectSuggestion(value) {
    const searchInput = document.getElementById('searchQuery');
    if (searchInput) {
        searchInput.value = value;
        hideAutocomplete();
        
        // Trigger search if form exists
        const form = document.getElementById('enhancedSearchForm');
        if (form) {
            form.dispatchEvent(new Event('submit', { cancelable: true }));
        }
    }
}

/**
 * Highlight query in text
 */
function highlightQuery(text, query) {
    if (!query) return escapeHtml(text);
    
    const escapedText = escapeHtml(text);
    const escapedQuery = escapeHtml(query);
    const regex = new RegExp(`(${escapedQuery})`, 'gi');
    
    return escapedText.replace(regex, '<span class="search-highlight">$1</span>');
}

/**
 * Get icon for suggestion type
 */
function getTypeIcon(type) {
    const icons = {
        'file_name': 'bi-file-earmark',
        'word': 'bi-text-paragraph',
        'fuzzy_match': 'bi-search'
    };
    return icons[type] || 'bi-circle';
}

/**
 * Get label for suggestion type
 */
function getTypeLabel(type) {
    const labels = {
        'file_name': 'File',
        'word': 'Word',
        'fuzzy_match': 'Similar'
    };
    return labels[type] || type;
}

/**
 * Setup keyboard navigation for autocomplete
 */
function setupKeyboardNavigation(searchInput) {
    if (!searchInput) return;

    searchInput.addEventListener('keydown', function(e) {
        const dropdown = document.getElementById('autocompleteDropdown');
        if (!dropdown || dropdown.style.display === 'none') {
            if (e.key === 'ArrowDown' && this.value.trim().length >= 2) {
                // Show autocomplete if hidden
                fetchAutocompleteSuggestions(this.value.trim());
            }
            return;
        }

        const items = dropdown.querySelectorAll('.autocomplete-item');
        if (items.length === 0) return;

        switch(e.key) {
            case 'ArrowDown':
                e.preventDefault();
                selectedSuggestionIndex = Math.min(selectedSuggestionIndex + 1, items.length - 1);
                updateSelection(items);
                break;
            case 'ArrowUp':
                e.preventDefault();
                selectedSuggestionIndex = Math.max(selectedSuggestionIndex - 1, -1);
                updateSelection(items);
                break;
            case 'Enter':
                e.preventDefault();
                if (selectedSuggestionIndex >= 0 && selectedSuggestionIndex < items.length) {
                    selectSuggestion(items[selectedSuggestionIndex].dataset.value);
                } else {
                    // Submit form if no suggestion selected
                    const form = document.getElementById('enhancedSearchForm');
                    if (form) {
                        form.dispatchEvent(new Event('submit', { cancelable: true }));
                    }
                }
                break;
            case 'Escape':
                e.preventDefault();
                hideAutocomplete();
                break;
        }
    });
}

/**
 * Update selected suggestion highlight
 */
function updateSelection(items) {
    items.forEach((item, index) => {
        if (index === selectedSuggestionIndex) {
            item.classList.add('active');
            item.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
        } else {
            item.classList.remove('active');
        }
    });
}

/**
 * Add advanced search options UI
 */
function addAdvancedSearchOptions() {
    const searchForm = document.getElementById('enhancedSearchForm');
    if (!searchForm) return;

    // Check if options already exist
    if (document.getElementById('advancedSearchOptions')) return;

    const optionsContainer = document.createElement('div');
    optionsContainer.id = 'advancedSearchOptions';
    optionsContainer.className = 'mb-3';
    optionsContainer.innerHTML = `
        <div class="card">
            <div class="card-header py-2">
                <button class="btn btn-link p-0 text-decoration-none w-100 text-start" 
                        type="button" 
                        data-bs-toggle="collapse" 
                        data-bs-target="#advancedOptionsCollapse"
                        aria-expanded="false">
                    <i class="bi bi-gear me-2"></i>
                    <strong>Advanced Search Options</strong>
                    <i class="bi bi-chevron-down float-end"></i>
                </button>
            </div>
            <div id="advancedOptionsCollapse" class="collapse">
                <div class="card-body">
                    <div class="row g-2">
                        <div class="col-md-6">
                            <div class="form-check form-switch">
                                <input class="form-check-input" type="checkbox" id="useBM25" checked>
                                <label class="form-check-label" for="useBM25">
                                    <i class="bi bi-graph-up me-1"></i>
                                    BM25 Ranking
                                    <small class="d-block text-muted">Better relevance scoring</small>
                                </label>
                            </div>
                        </div>
                        <div class="col-md-6">
                            <div class="form-check form-switch">
                                <input class="form-check-input" type="checkbox" id="useExpansion" checked>
                                <label class="form-check-label" for="useExpansion">
                                    <i class="bi bi-arrows-angle-expand me-1"></i>
                                    Query Expansion
                                    <small class="d-block text-muted">Include synonyms</small>
                                </label>
                            </div>
                        </div>
                        <div class="col-md-6">
                            <div class="form-check form-switch">
                                <input class="form-check-input" type="checkbox" id="useFuzzy" checked>
                                <label class="form-check-label" for="useFuzzy">
                                    <i class="bi bi-search me-1"></i>
                                    Fuzzy Matching
                                    <small class="d-block text-muted">Typo tolerance</small>
                                </label>
                            </div>
                        </div>
                        <div class="col-md-6">
                            <div class="form-check form-switch">
                                <input class="form-check-input" type="checkbox" id="useAdvanced" checked>
                                <label class="form-check-label" for="useAdvanced">
                                    <i class="bi bi-magic me-1"></i>
                                    Advanced Algorithms
                                    <small class="d-block text-muted">Enable all features</small>
                                </label>
                            </div>
                        </div>
                    </div>
                    <div class="mt-3">
                        <small class="text-muted">
                            <i class="bi bi-info-circle me-1"></i>
                            <strong>Tip:</strong> Use quotes for exact phrases, e.g., "financial report"
                        </small>
                    </div>
                </div>
            </div>
        </div>
    `;

    // Insert after search input
    const searchInput = document.getElementById('searchQuery');
    if (searchInput && searchInput.parentElement) {
        searchInput.parentElement.insertBefore(optionsContainer, searchInput.nextSibling);
    }
}

/**
 * Get advanced search options from form
 */
export function getAdvancedSearchOptions() {
    return {
        use_advanced: document.getElementById('useAdvanced')?.checked !== false,
        use_bm25: document.getElementById('useBM25')?.checked !== false,
        use_expansion: document.getElementById('useExpansion')?.checked !== false,
        use_fuzzy: document.getElementById('useFuzzy')?.checked !== false
    };
}

/**
 * Enhance search results display with relevance scores
 */
export function enhanceResultsDisplay(results) {
    if (!results || !Array.isArray(results)) return results;

    return results.map(result => {
        // Add relevance badge if score is available
        if (result.relevance_score !== undefined && result.relevance_score > 0) {
            result.relevance_display = result.relevance_score.toFixed(2);
            result.relevance_percentage = Math.min(100, Math.round(result.relevance_score * 10));
        }
        return result;
    });
}

/**
 * Format search result with highlights
 */
export function formatSearchResult(result, query) {
    if (!result) return '';

    const fileName = escapeHtml(result.file_name || 'Unknown');
    const highlightedName = highlightQuery(fileName, query);
    
    let html = `
        <div class="search-result-item mb-3 p-3 border rounded">
            <div class="d-flex justify-content-between align-items-start">
                <div class="flex-grow-1">
                    <h6 class="mb-2">
                        <a href="/file/${result.id}" class="text-decoration-none">
                            ${highlightedName}
                        </a>
                        ${result.relevance_score !== undefined ? `
                            <span class="badge bg-info ms-2" title="Relevance Score">
                                ${result.relevance_score.toFixed(2)}
                            </span>
                        ` : ''}
                    </h6>
                    <div class="small text-muted mb-2">
                        <span class="me-3">
                            <i class="bi bi-building me-1"></i>${escapeHtml(result.source_name || 'Unknown')}
                        </span>
                        <span class="me-3">
                            <i class="bi bi-diagram-3 me-1"></i>${escapeHtml(result.side_name || 'Unknown')}
                        </span>
                        <span class="me-3">
                            <i class="bi bi-calendar me-1"></i>${result.file_date || 'N/A'}
                        </span>
                        <span class="badge bg-secondary">${result.file_type || 'Unknown'}</span>
                    </div>
    `;

    // Add line matches if available
    if (result.line_matches && result.line_matches.length > 0) {
        html += '<div class="mt-2"><small class="text-muted">Matching content:</small><ul class="list-unstyled ms-3 mt-1">';
        result.line_matches.slice(0, 3).forEach(match => {
            html += `
                <li class="small mb-1">
                    <span class="text-muted">${escapeHtml(match.location || ('Line ' + match.line_number))}:</span>
                    <span class="ms-2">${match.highlighted_line || escapeHtml(match.line_text)}</span>
                </li>
            `;
        });
        if (result.line_match_count > 3) {
            html += `<li class="small text-muted">... and ${result.line_match_count - 3} more matches</li>`;
        }
        html += '</ul></div>';
    }

    html += `
                </div>
            </div>
        </div>
    `;

    return html;
}

// Export API
export default {
    initializeAdvancedSearch,
    getAdvancedSearchOptions,
    enhanceResultsDisplay,
    formatSearchResult,
    fetchAutocompleteSuggestions,
    hideAutocomplete
};

