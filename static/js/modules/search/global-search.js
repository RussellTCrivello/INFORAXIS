/**
 * Global Search Module
 * Handles full-text search, sorting, filters, history, and saved searches
 * Migrated from enhanced-search.js to use new architecture
 */

import { apiGet, apiPost, apiDelete } from '../api/api-client.js';
import { endpoints } from '../api/endpoints.js';
import { escapeHtml, getCSRFToken } from '../core/utils.js';
import notificationSystem from '../ui/notifications.js';
import advancedSearch from './advanced-search.js';

// State management
const searchState = {
    currentQuery: '',
    currentFilters: {},
    currentSort: { by: 'relevance', order: 'desc' },
    currentPage: 1,
    perPage: 10,
    results: [],
    totalResults: 0,
    totalPages: 0,
    loading: false
};

// OPTIMIZATION: Request cancellation for concurrent searches
let currentSearchController = null;

/**
 * Initialize search interface
 */
export function initializeSearch() {
    const searchForm = document.getElementById('enhancedSearchForm');
    const searchInput = document.getElementById('searchQuery');
    const sortSelect = document.getElementById('sortBy');
    const sortOrderSelect = document.getElementById('sortOrder');
    const exportBtn = document.getElementById('exportResultsBtn');
    const saveSearchBtn = document.getElementById('saveSearchBtn');

    if (searchForm) {
        searchForm.addEventListener('submit', handleSearchSubmit);
    }

    if (searchInput) {
        // OPTIMIZED: Debounced search with request cancellation
        let searchTimeout;
        searchInput.addEventListener('input', function() {
            // Cancel any pending search
            if (currentSearchController) {
                currentSearchController.abort();
                currentSearchController = null;
            }

            clearTimeout(searchTimeout);

            // Clear results immediately if query is too short
            if (this.value.trim().length < 2) {
                clearResults();
                return;
            }

            searchTimeout = setTimeout(() => {
                if (this.value.trim().length >= 2) {
                    performSearch();
                }
            }, 300);
        });
    }

    if (sortSelect) {
        sortSelect.addEventListener('change', function() {
            searchState.currentSort.by = this.value;
            performSearch();
        });
    }

    if (sortOrderSelect) {
        sortOrderSelect.addEventListener('change', function() {
            searchState.currentSort.order = this.value;
            performSearch();
        });
    }

    if (exportBtn) {
        exportBtn.addEventListener('click', handleExport);
    }

    if (saveSearchBtn) {
        saveSearchBtn.addEventListener('click', showSaveSearchModal);
    }

    // Filter change handlers
    setupFilterHandlers();
}

/**
 * Setup filter change handlers
 */
function setupFilterHandlers() {
    const filterInputs = document.querySelectorAll('.search-filter');
    filterInputs.forEach(input => {
        input.addEventListener('change', function() {
            updateFilters();
            performSearch();
        });
    });
}

/**
 * Update filters from form
 */
function updateFilters() {
    searchState.currentFilters = {
        file_type: document.getElementById('filterFileType')?.value || '',
        source_id: document.getElementById('filterSourceId')?.value || '',
        side_id: document.getElementById('filterSideId')?.value || '',
        date_from: document.getElementById('filterDateFrom')?.value || '',
        date_to: document.getElementById('filterDateTo')?.value || '',
        category_id: document.getElementById('filterCategoryId')?.value || ''
    };
}

/**
 * Handle search form submission
 */
function handleSearchSubmit(e) {
    e.preventDefault();
    searchState.currentPage = 1;
    performSearch();
}

/**
 * Perform search using enhanced API
 */
export async function performSearch() {
    const searchInput = document.getElementById('searchQuery');
    if (!searchInput) return;

    const query = searchInput.value.trim();
    if (!query || query.length < 2) {
        clearResults();
        return;
    }

    searchState.currentQuery = query;
    updateFilters();
    searchState.loading = true;

    showLoading();

    try {
        // OPTIMIZATION: Cancel previous search request if still pending
        if (currentSearchController) {
            currentSearchController.abort();
        }

        // Create new AbortController for this search
        currentSearchController = new AbortController();
        const signal = currentSearchController.signal;

        // Check if comprehensive search is enabled
        const searchAllData = document.getElementById('searchAllData')?.checked || false;

        // Get advanced search options
        const advancedOptions = advancedSearch.getAdvancedSearchOptions();

        const params = {
            query: query,
            page: searchState.currentPage,
            per_page: searchState.perPage,
            sort_by: searchState.currentSort.by,
            sort_order: searchState.currentSort.order,
            use_fulltext: searchAllData ? 'false' : 'true',
            search_all_data: searchAllData ? 'true' : 'false',
            // Advanced search options
            use_advanced: advancedOptions.use_advanced ? 'true' : 'false',
            use_bm25: advancedOptions.use_bm25 ? 'true' : 'false',
            use_expansion: advancedOptions.use_expansion ? 'true' : 'false',
            use_fuzzy: advancedOptions.use_fuzzy ? 'true' : 'false',
            ...Object.fromEntries(
                Object.entries(searchState.currentFilters)
                    .filter(([_, v]) => v !== '')
            )
        };

        // Analyst-categorization search scope (FR-2.x): included whenever the
        // page renders the explicit scope control (#analystScopeSelect). The
        // server persists the selection in the session (FR-2.3).
        const scopeSelect = document.getElementById('analystScopeSelect');
        if (scopeSelect && scopeSelect.value) {
            params.scope = scopeSelect.value;
        }

        const apiUrl = endpoints.search(params);
        const data = await apiGet(apiUrl, {}, { signal });

        // Clear controller after successful fetch
        currentSearchController = null;

        // Enhance results with advanced search features
        let results = data.results || [];
        results = advancedSearch.enhanceResultsDisplay(results);

        searchState.results = results;
        searchState.totalResults = data.pagination?.total || 0;
        searchState.totalPages = data.pagination?.total_pages || 0;

        displayResults({ ...data, results: results });
        updatePagination(data.pagination);

    } catch (error) {
        // Don't show error if request was aborted (user typed new query)
        if (error.name === 'AbortError') {
            // Silently handle abort - this is expected behavior
            return;
        }

        console.error('Search error:', error);
        notificationSystem.error('Error performing search: ' + (error.message || 'Unknown error'));
    } finally {
        searchState.loading = false;
        hideLoading();
        // Clear controller reference
        if (currentSearchController) {
            currentSearchController = null;
        }
    }
}

/**
 * Display search results
 */
function displayResults(data) {
    const resultsContainer = document.getElementById('searchResults');
    if (!resultsContainer) return;

    if (!data.results || data.results.length === 0) {
        resultsContainer.innerHTML = `
            <div class="text-center text-muted py-5">
                <i class="bi bi-search display-4 d-block mb-3"></i>
                <p>No results found for "${escapeHtml(searchState.currentQuery)}"</p>
            </div>
        `;
        return;
    }

    let html = `
        <div class="d-flex justify-content-between align-items-center mb-3">
            <div>
                <strong>${data.pagination.total}</strong> results found
            </div>
            <div class="btn-group">
                <button class="btn btn-sm btn-outline-primary" onclick="window.fms.search.global.exportResults('csv')">
                    <i class="bi bi-file-earmark-spreadsheet me-1"></i>CSV
                </button>
                <button class="btn btn-sm btn-outline-primary" onclick="window.fms.search.global.exportResults('excel')">
                    <i class="bi bi-file-earmark-excel me-1"></i>Excel
                </button>
                <button class="btn btn-sm btn-outline-primary" onclick="window.fms.search.global.exportResults('json')">
                    <i class="bi bi-file-earmark-code me-1"></i>JSON
                </button>
            </div>
        </div>
    `;

    // Group results by type for better organization
    const resultsByType = {};
    data.results.forEach(result => {
        const resultType = result.result_type || 'file';
        if (!resultsByType[resultType]) {
            resultsByType[resultType] = [];
        }
        resultsByType[resultType].push(result);
    });

    // Display results grouped by type
    const typeLabels = {
        'file': { icon: 'bi-file-earmark', label: 'Files', color: 'primary' },
        'category': { icon: 'bi-tags', label: 'Categories', color: 'success' },
        'keyword': { icon: 'bi-key', label: 'Keywords', color: 'warning' },
        'source': { icon: 'bi-building', label: 'Sources', color: 'info' },
        'side': { icon: 'bi-diagram-3', label: 'Sides', color: 'secondary' },
        'word': { icon: 'bi-text-paragraph', label: 'Words', color: 'dark' },
        'title': { icon: 'bi-heading', label: 'Titles', color: 'primary' }
    };

    Object.keys(resultsByType).forEach(resultType => {
        const typeInfo = typeLabels[resultType] || { icon: 'bi-circle', label: resultType, color: 'secondary' };
        const typeResults = resultsByType[resultType];

        html += `
            <div class="mb-4">
                <h5 class="mb-3">
                    <i class="bi ${typeInfo.icon} me-2"></i>
                    ${typeInfo.label} (${typeResults.length})
                </h5>
        `;

        typeResults.forEach(result => {
            const resultType = result.result_type || 'file';

            // Build result HTML based on type
            let resultHtml = '';
            let resultName = result.name || result.file_name || 'Unknown';
/** Detail-page URL carrying the current search so the term is located
 *  when the file opens (?q= alias on the file routes). */
function fileDetailHref(fileId) {
    const qs = searchState.currentQuery
        ? `?q=${encodeURIComponent(searchState.currentQuery)}`
        : '';
    return `/file/${fileId}${qs}`;
}

            let resultLink = '#';
            let resultDetails = '';

            switch(resultType) {
                case 'file':
                    resultLink = fileDetailHref(result.id);
                    // Use advanced search formatting if available
                    const formattedResult = advancedSearch.formatSearchResult(result, searchState.currentQuery);
                    if (formattedResult) {
                        resultHtml = formattedResult;
                        break;
                    }
                    // Fallback to original formatting
                    resultDetails = `
                        <small class="text-muted d-block mb-1">
                            <span class="me-3">
                                <i class="bi bi-building me-1"></i>${escapeHtml(result.source_name || 'Unknown')}
                            </span>
                            <span class="me-3">
                                <i class="bi bi-diagram-3 me-1"></i>${escapeHtml(result.side_name || 'Unknown')}
                            </span>
                            <span class="me-3">
                                <i class="bi bi-calendar me-1"></i>${result.date || result.file_date || 'N/A'}
                            </span>
                            ${result.relevance_score !== undefined ? `
                                <span class="badge bg-info ms-2" title="Relevance Score">
                                    ${result.relevance_score.toFixed(2)}
                                </span>
                            ` : ''}
                        </small>
                        <div class="d-flex gap-2 mt-2">
                            <button class="btn btn-sm btn-outline-secondary" onclick="window.fms.search.global.previewFile(${result.id})">
                                <i class="bi bi-eye me-1"></i>Preview
                            </button>
                            <span class="badge bg-secondary">${result.type || result.file_type || 'Unknown'}</span>
                        </div>
                    `;
                    break;
                case 'category':
                    resultLink = `/category/${result.id}`;
                    resultDetails = `
                        <small class="text-muted d-block mb-1">
                            <span class="me-3">
                                <i class="bi bi-file-earmark me-1"></i>${result.file_count || 0} files
                            </span>
                        </small>
                    `;
                    break;
                case 'keyword':
                    resultLink = `/keywords/${result.id}`;
                    resultDetails = `
                        <small class="text-muted d-block mb-1">
                            <span class="me-3">
                                <i class="bi bi-file-earmark me-1"></i>Used in ${result.usage_count || 0} files
                            </span>
                        </small>
                    `;
                    break;
                case 'source':
                    resultLink = `/source/${result.id}`;
                    resultDetails = `
                        <small class="text-muted d-block mb-1">
                            <span class="me-3">
                                <i class="bi bi-briefcase me-1"></i>${escapeHtml(result.job || 'N/A')}
                            </span>
                            <span class="me-3">
                                <i class="bi bi-geo-alt me-1"></i>${escapeHtml(result.country || 'N/A')}
                            </span>
                            <span class="me-3">
                                <i class="bi bi-hash me-1"></i>${result.hash_count || 0} hashes
                            </span>
                        </small>
                    `;
                    break;
                case 'side':
                    resultLink = `/side/${result.id}`;
                    resultDetails = `
                        <small class="text-muted d-block mb-1">
                            <span class="me-3">
                                <i class="bi bi-hash me-1"></i>${result.hash_count || 0} hashes
                            </span>
                            <span class="me-3">
                                <i class="bi bi-calendar me-1"></i>${result.date_creation || 'N/A'}
                            </span>
                        </small>
                    `;
                    break;
                case 'word':
                    resultLink = `/word/${result.id}`;
                    resultDetails = `
                        <small class="text-muted d-block mb-1">
                            <span class="me-3">
                                <i class="bi bi-file-earmark me-1"></i>${result.file_count || 0} files
                            </span>
                        </small>
                    `;
                    break;
                case 'title':
                    resultLink = result.path_id ? fileDetailHref(result.path_id) : '#';
                    resultDetails = `
                        <small class="text-muted d-block mb-1">
                            ${result.file_name ? `<span class="me-3"><i class="bi bi-file-earmark me-1"></i>${escapeHtml(result.file_name)}</span>` : ''}
                            <span class="badge bg-secondary">${result.status || 'Main'}</span>
                        </small>
                    `;
                    break;
            }

            html += `
                <div class="list-group-item list-group-item-action">
                    <div class="d-flex justify-content-between align-items-start">
                        <div class="flex-grow-1">
                            <h6 class="mb-1">
                                <i class="bi ${typeInfo.icon} me-2"></i>
                                <a href="${resultLink}" class="text-decoration-none">
                                    ${escapeHtml(resultName)}
                                </a>
                                <span class="badge bg-${typeInfo.color} ms-2">${typeInfo.label}</span>
                            </h6>
                            ${resultDetails}
                            ${result.relevance !== undefined ? `<span class="badge bg-info mt-2">Relevance: ${result.relevance.toFixed(2)}</span>` : ''}
                        </div>
                    </div>
                </div>
            `;
        });

        html += '</div>';
    });

    // If no results by type, show empty message
    if (Object.keys(resultsByType).length === 0) {
        html = `
            <div class="text-center text-muted py-5">
                <i class="bi bi-search display-4 d-block mb-3"></i>
                <p>No results found for "${escapeHtml(searchState.currentQuery)}"</p>
            </div>
        `;
    }

    resultsContainer.innerHTML = html;
}

/**
 * Update pagination UI
 */
function updatePagination(pagination) {
    const paginationContainer = document.getElementById('searchPagination');
    if (!paginationContainer || !pagination) return;

    // Hide pagination if there's only one page or no pages
    if (!pagination.total_pages || pagination.total_pages <= 1) {
        paginationContainer.innerHTML = '';
        return;
    }

    // Use unified pagination
    import('../../modules/rendering/unified-pagination.js').then(module => {
        module.renderUnifiedPagination({
            currentPage: pagination.page,
            totalPages: pagination.total_pages,
            containerId: 'searchPagination',
            onPageChange: (targetPage) => {
                if (window.fms && window.fms.search && window.fms.search.global) {
                    window.fms.search.global.goToPage(targetPage);
                }
            },
            urlParams: {},
            showInfo: true,
            showJump: pagination.total_pages > 5,
            baseUrl: window.location.pathname
        });
    }).catch(err => {
        console.error('Error loading unified pagination:', err);
        // Fallback to old pagination
        let html = '<nav><ul class="pagination justify-content-center">';
        html += `<li class="page-item ${!pagination.has_prev ? 'disabled' : ''}"><a class="page-link" href="#" onclick="${pagination.has_prev ? `window.fms.search.global.goToPage(${pagination.page - 1});` : ''} return false;" ${!pagination.has_prev ? 'aria-disabled="true" tabindex="-1"' : ''}>Previous</a></li>`;
        for (let i = 1; i <= pagination.total_pages; i++) {
            if (i === 1 || i === pagination.total_pages || (i >= pagination.page - 2 && i <= pagination.page + 2)) {
                html += `<li class="page-item ${i === pagination.page ? 'active' : ''}"><a class="page-link" href="#" onclick="window.fms.search.global.goToPage(${i}); return false;" ${i === pagination.page ? 'aria-current="page"' : ''}>${i}</a></li>`;
            } else if (i === pagination.page - 3 || i === pagination.page + 3) {
                html += '<li class="page-item disabled"><span class="page-link">...</span></li>';
            }
        }
        html += `<li class="page-item ${!pagination.has_next ? 'disabled' : ''}"><a class="page-link" href="#" onclick="${pagination.has_next ? `window.fms.search.global.goToPage(${pagination.page + 1});` : ''} return false;" ${!pagination.has_next ? 'aria-disabled="true" tabindex="-1"' : ''}>Next</a></li>`;
        html += '</ul></nav>';
        paginationContainer.innerHTML = html;
    });
}

/**
 * Go to specific page
 */
export function goToPage(page) {
    searchState.currentPage = page;
    performSearch();
    window.scrollTo({ top: 0, behavior: 'smooth' });
}

/**
 * Export search results
 */
export async function exportResults(format) {
    if (!searchState.results || searchState.results.length === 0) {
        notificationSystem.warning('No results to export');
        return;
    }

    try {
        // Get CSRF token with fallback
        let csrfToken = getCSRFToken();
        if (!csrfToken) {
            const { getCSRFTokenAsync } = await import('../core/utils.js');
            csrfToken = await getCSRFTokenAsync();
        }

        // Handle blob response - need to use fetch directly for blob
        const response = await fetch(endpoints.searchExport(), {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrfToken
            },
            body: JSON.stringify({
                results: searchState.results,
                format: format,
                filename: `search_results_${new Date().toISOString().split('T')[0]}`
            })
        });

        if (!response.ok) {
            throw new Error('Export failed');
        }

        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `search_results.${format === 'excel' ? 'xlsx' : format}`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        window.URL.revokeObjectURL(url);

    } catch (error) {
        console.error('Export error:', error);
        notificationSystem.error('Error exporting results: ' + (error.message || 'Unknown error'));
    }
}

/**
 * Preview file
 */
export async function previewFile(fileId) {
    try {
        const apiUrl = endpoints.filePreview(fileId, 1200, 800);
        const data = await apiGet(apiUrl);

        if (data.preview_type === 'error') {
            notificationSystem.error('Preview error: ' + (data.error || 'Unknown error'));
            return;
        }

        data.file_id = fileId;
        showPreviewModal(data);

    } catch (error) {
        console.error('Preview error:', error);
        notificationSystem.error('Error loading preview: ' + (error.message || 'Unknown error'));
    }
}

/**
 * Show preview modal
 */
function showPreviewModal(previewData) {
    // Create or get modal
    let modal = document.getElementById('filePreviewModal');
    if (!modal) {
        modal = document.createElement('div');
        modal.id = 'filePreviewModal';
        modal.className = 'modal fade';
        modal.innerHTML = `
            <div class="modal-dialog modal-lg">
                <div class="modal-content">
                    <div class="modal-header">
                        <h5 class="modal-title">File Preview</h5>
                        <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                    </div>
                    <div class="modal-body" id="previewModalBody"></div>
                </div>
            </div>
        `;
        document.body.appendChild(modal);
    }

    const body = document.getElementById('previewModalBody');
    renderPreviewBody(body, previewData);

    // Show modal using Bootstrap
    if (typeof bootstrap !== 'undefined' && bootstrap.Modal) {
        const bsModal = new bootstrap.Modal(modal);
        bsModal.show();
    } else {
        // Fallback if Bootstrap not available
        modal.style.display = 'block';
        modal.classList.add('show');
    }
}

/**
 * Render the preview body with the SAME type-aware formatting used on the
 * content pages (tables for spreadsheets, paragraphs for documents, ...),
 * so every content display interface shows identical output. Falls back to
 * the previous plain rendering if the formatter is unavailable.
 */
async function renderPreviewBody(body, previewData) {
    let content = '';

    if (previewData.preview_type === 'image') {
        content = `<img src="${previewData.data}" class="img-fluid" alt="Preview">`;
    } else if (previewData.preview_type === 'pdf' || previewData.preview_type === 'document' || previewData.preview_type === 'text') {
        let text;
        if (previewData.preview_type === 'document' && Array.isArray(previewData.data)) {
            // Spreadsheet previews arrive as row arrays - render them as a
            // table through the shared excel formatter (TSV round-trip).
            text = previewData.data
                .map(row => (row || []).map(cell => String(cell == null ? '' : cell)).join('\t'))
                .join('\n');
        } else {
            text = typeof previewData.data === 'string' ? previewData.data : JSON.stringify(previewData.data, null, 2);
        }

        let formatted = '';
        try {
            const formatter = await import('../content-formatter.js');
            const name = previewData.file_name || previewData.file_type || '';
            const ext = name.includes('.') ? name.split('.').pop() : (previewData.file_type || 'txt');
            formatted = formatter.formatContentByType(
                text, ext, previewData.file_path || '', previewData.file_id || null);
        } catch (e) {
            console.warn('Formatted preview unavailable, using plain text:', e);
        }

        if (formatted) {
            ensureFormattedContentStyles();
            content = `<div class="formatted-content-wrapper" style="max-height: 500px; overflow-y: auto;">${formatted}</div>`;
        } else {
            content = `<pre class="bg-light p-3" style="max-height: 500px; overflow-y: auto;">${escapeHtml(text)}</pre>`;
        }
    } else {
        content = `<p class="text-muted">${previewData.message || 'Preview not available'}</p>`;
    }

    body.innerHTML = content;
}

/** Load the shared formatted-content stylesheet on demand. */
function ensureFormattedContentStyles() {
    if (document.getElementById('formatted-content-preview-css')) return;
    const link = document.createElement('link');
    link.id = 'formatted-content-preview-css';
    link.rel = 'stylesheet';
    link.href = '/static/css/formatted-content.css';
    document.head.appendChild(link);
}

/**
 * Load search history
 */
export async function loadSearchHistory() {
    try {
        const apiUrl = endpoints.searchHistory(10);
        const data = await apiGet(apiUrl);

        const historyContainer = document.getElementById('searchHistory');
        if (!historyContainer) return;

        if (!data.history || data.history.length === 0) {
            historyContainer.innerHTML = '<p class="text-muted small">No search history</p>';
            return;
        }

        let html = '<ul class="list-group list-group-flush">';
        data.history.forEach(item => {
            html += `
                <li class="list-group-item">
                    <div class="d-flex justify-content-between align-items-center">
                        <div>
                            <a href="#" onclick="window.fms.search.global.loadHistorySearch('${escapeHtml(item.query)}'); return false;" class="text-decoration-none">
                                ${escapeHtml(item.query)}
                            </a>
                            <small class="text-muted d-block">${new Date(item.timestamp).toLocaleString()}</small>
                        </div>
                        <span class="badge bg-secondary">${item.result_count} results</span>
                    </div>
                </li>
            `;
        });
        html += '</ul>';

        historyContainer.innerHTML = html;

    } catch (error) {
        console.error('Error loading search history:', error);
    }
}

/**
 * Load saved searches
 */
export async function loadSavedSearches() {
    try {
        const apiUrl = endpoints.searchSaved();
        const data = await apiGet(apiUrl);

        const savedContainer = document.getElementById('savedSearches');
        if (!savedContainer) return;

        if (!data.searches || data.searches.length === 0) {
            savedContainer.innerHTML = '<p class="text-muted small">No saved searches</p>';
            return;
        }

        let html = '<ul class="list-group list-group-flush">';
        data.searches.forEach(search => {
            html += `
                <li class="list-group-item">
                    <div class="d-flex justify-content-between align-items-center">
                        <div>
                            <a href="#" onclick="window.fms.search.global.loadSavedSearch(${search.id}); return false;" class="text-decoration-none fw-bold">
                                ${escapeHtml(search.name)}
                            </a>
                            <small class="text-muted d-block">${escapeHtml(search.query)}</small>
                        </div>
                    </div>
                </li>
            `;
        });
        html += '</ul>';

        savedContainer.innerHTML = html;

    } catch (error) {
        console.error('Error loading saved searches:', error);
    }
}

/**
 * Load history search
 */
export function loadHistorySearch(query) {
    document.getElementById('searchQuery').value = query;
    searchState.currentPage = 1;
    performSearch();
}

/**
 * Load saved search
 */
export async function loadSavedSearch(searchId) {
    try {
        const apiUrl = endpoints.searchSavedById(searchId);
        const data = await apiGet(apiUrl);

        if (data.search) {
            document.getElementById('searchQuery').value = data.search.query;
            if (data.search.filters) {
                Object.entries(data.search.filters).forEach(([key, value]) => {
                    const input = document.getElementById(`filter${key.charAt(0).toUpperCase() + key.slice(1)}`);
                    if (input) input.value = value;
                });
            }
            searchState.currentPage = 1;
            performSearch();
        }

    } catch (error) {
        console.error('Error loading saved search:', error);
        notificationSystem.error('Error loading saved search: ' + (error.message || 'Unknown error'));
    }
}

/**
 * Delete saved search
 */
export async function deleteSavedSearch(searchId) {
    if (!confirm('Delete this saved search?')) return;

    try {
        const apiUrl = endpoints.searchSavedById(searchId);
        await apiDelete(apiUrl);

        loadSavedSearches();
        notificationSystem.success('Saved search deleted');

    } catch (error) {
        console.error('Error deleting saved search:', error);
        notificationSystem.error('Error deleting saved search: ' + (error.message || 'Unknown error'));
    }
}

/**
 * Show save search modal
 */
export async function showSaveSearchModal() {
    const query = document.getElementById('searchQuery')?.value.trim();
    if (!query) {
        notificationSystem.warning('Please enter a search query first');
        return;
    }

    const name = await prompt('Enter a name for this search:', query);
    if (!name) return;

    saveSearch(name, query);
}

/**
 * Save search
 */
export async function saveSearch(name, query) {
    try {
        const apiUrl = endpoints.searchSaved();
        await apiPost(apiUrl, {
            name: name,
            query: query,
            filters: searchState.currentFilters
        });

        loadSavedSearches();
        notificationSystem.success('Search saved successfully');

    } catch (error) {
        console.error('Error saving search:', error);
        notificationSystem.error('Error saving search: ' + (error.message || 'Unknown error'));
    }
}

/**
 * Clear results
 */
function clearResults() {
    const resultsContainer = document.getElementById('searchResults');
    if (resultsContainer) {
        resultsContainer.innerHTML = '';
    }
    const paginationContainer = document.getElementById('searchPagination');
    if (paginationContainer) {
        paginationContainer.innerHTML = '';
    }
}

/**
 * Show loading indicator
 */
function showLoading() {
    const resultsContainer = document.getElementById('searchResults');
    if (resultsContainer) {
        resultsContainer.innerHTML = '<div class="text-center py-5"><div class="spinner-border" role="status"><span class="visually-hidden">Loading...</span></div></div>';
    }
}

/**
 * Hide loading indicator
 */
function hideLoading() {
    // Loading is replaced by results
}

/**
 * Handle export button click
 */
function handleExport(e) {
    e.preventDefault();
    const format = e.target.dataset.format || 'csv';
    exportResults(format);
}

// Initialize on page load
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

// Export API
export default {
    initializeSearch,
    performSearch,
    goToPage,
    exportResults,
    previewFile,
    loadHistorySearch,
    loadSavedSearch,
    deleteSavedSearch,
    saveSearch,
    showSaveSearchModal,
    loadSearchHistory,
    loadSavedSearches
};
