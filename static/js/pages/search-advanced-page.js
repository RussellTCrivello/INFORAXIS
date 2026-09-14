/**
 * Advanced Search Page JavaScript - Google/YouTube-like Implementation
 * Complete overhaul with professional filtering and intelligent algorithms
 */

// Global state
/** Detail-page URL that carries the originating content search so the
 *  term is located precisely when the file opens (?q= alias). */
function fileDetailHref(fileId) {
    const params = new URLSearchParams();
    if (searchState.query) {
        params.set('q', searchState.query);
        params.set('case_sensitive', String(!!(searchState.options && searchState.options.caseSensitive)));
        params.set('whole_word', String(!!(searchState.options && searchState.options.wholeWord)));
    }
    const qs = params.toString();
    return `/file/${fileId}${qs ? '?' + qs : ''}`;
}

const searchState = {
    query: '',
    filters: {
        fileType: [],
        categories: [],
        analystCategories: [],
        sources: [],
        sides: [],
        dateFrom: '',
        dateTo: '',
        status: ['Read']
    },
    options: {
        caseSensitive: false,
        wholeWord: false,
        useFuzzy: true
    },
    // Analyst-categorization search scope (FR-2.x): 'uncategorized' (default),
    // 'all' or 'categorized'. Operates ONLY on analyst categorization status.
    scope: 'uncategorized',
    // Manual categorization state (FR-1.2 / FR-1.3)
    canCategorize: false,
    analystCategories: [],
    selectedIds: new Set(),
    results: [],
    currentPage: 1,
    resultsPerPage: 20,
    totalResults: 0,
    searchTime: 0,
    suggestions: [],
    searchHistory: []
};

// Initialize on page load
document.addEventListener('DOMContentLoaded', function() {
    console.log('Advanced Search page loaded - Google-like implementation');
    initializePageData();
    initializeSearch();
    initializeScopeSelector();
    loadFilterOptions();
    loadSearchHistory();
    setupEventListeners();
});

// Read server-provided page data (initial scope, permissions, translations)
function initializePageData() {
    const pageDataEl = document.getElementById('search-advanced-page-data');
    if (!pageDataEl) return;
    try {
        const data = JSON.parse(pageDataEl.textContent);
        if (data.initialScope && ['uncategorized', 'all', 'categorized'].includes(data.initialScope)) {
            searchState.scope = data.initialScope;
        }
        searchState.canCategorize = !!data.canCategorize;
        const radio = document.querySelector(`input[name="analystScope"][value="${searchState.scope}"]`);
        if (radio) radio.checked = true;
        // Viewers cannot categorize: hide the manual-categorization bar entirely.
        if (!searchState.canCategorize) {
            const bar = document.getElementById('analystCategorizationBar');
            if (bar) bar.remove();
        }
    } catch (e) {
        console.warn('Could not parse page data', e);
    }
}

// Wire the scope radio group (FR-2.2). Changing scope re-runs the search so
// the result set immediately reflects the newly selected scope.
function initializeScopeSelector() {
    document.querySelectorAll('input[name="analystScope"]').forEach(radio => {
        radio.addEventListener('change', function() {
            if (this.checked) {
                searchState.scope = this.value;
                // The server persists this selection in the session (FR-2.3)
                // because the scope parameter travels with every /api/search
                // request below.
                if (document.getElementById('searchResultsSection').style.display !== 'none') {
                    executeAdvancedSearch();
                }
            }
        });
    });
}

// Initialize search functionality
function initializeSearch() {
    const mainInput = document.getElementById('mainSearchInput');
    if (!mainInput) return;
    
    // Real-time search suggestions
    let suggestionTimeout;
    mainInput.addEventListener('input', function(e) {
        const query = e.target.value.trim();
        searchState.query = query;
        
        // Show/hide clear button
        const clearBtn = document.getElementById('clearSearchBtn');
        if (clearBtn) {
            clearBtn.style.display = query ? 'block' : 'none';
        }
        
        // Debounce suggestions
        clearTimeout(suggestionTimeout);
        if (query.length >= 2) {
            suggestionTimeout = setTimeout(() => {
                loadSearchSuggestions(query);
            }, 300);
        } else {
            hideSuggestions();
        }
    });
    
    // Enter key to search
    mainInput.addEventListener('keydown', function(e) {
        if (e.key === 'Enter') {
            e.preventDefault();
            executeAdvancedSearch();
        } else if (e.key === 'Escape') {
            hideSuggestions();
        }
    });
    
    // Clear search
    const clearBtn = document.getElementById('clearSearchBtn');
    if (clearBtn) {
        clearBtn.addEventListener('click', function() {
            mainInput.value = '';
            searchState.query = '';
            clearBtn.style.display = 'none';
            hideSuggestions();
            mainInput.focus();
        });
    }
}

// Setup event listeners
function setupEventListeners() {
    // Filter select changes
    ['fileType', 'categoriesSelect', 'analystCategoriesFilter', 'sourcesSelect', 'sidesSelect'].forEach(id => {
        const element = document.getElementById(id);
        if (element) {
            element.addEventListener('change', updateFilterChips);
        }
    });
    
    // Date changes
    ['dateFrom', 'dateTo'].forEach(id => {
        const element = document.getElementById(id);
        if (element) {
            element.addEventListener('change', updateFilterChips);
        }
    });
    
    // Status checkboxes
    ['statusRead', 'statusUnread'].forEach(id => {
        const element = document.getElementById(id);
        if (element) {
            element.addEventListener('change', updateFilterChips);
        }
    });
}

// Load filter options
async function loadFilterOptions() {
    try {
        // Load categories
        const categoriesRes = await fetch('/api/categories');
        const categories = await categoriesRes.json();
        const categoriesSelect = document.getElementById('categoriesSelect');
        if (categoriesSelect && Array.isArray(categories)) {
            categoriesSelect.innerHTML = categories.map(c =>
                `<option value="${c.id}">${escapeHtml(c.name)}</option>`
            ).join('');
        }
        
        // Load sources (advanced-filters panel - the single home for
        // source/side scoping since the old "Search Within" block was
        // merged into it)
        const sourcesRes = await fetch('/api/sources');
        const sources = await sourcesRes.json();

        const sourcesSelect = document.getElementById('sourcesSelect');
        if (sourcesSelect && Array.isArray(sources)) {
            sourcesSelect.innerHTML = sources.map(s =>
                `<option value="${s.id}">${escapeHtml(s.name)}</option>`
            ).join('');
        }

        // Load sides
        const sidesRes = await fetch('/api/sides');
        const sides = await sidesRes.json();

        const sidesSelect = document.getElementById('sidesSelect');
        if (sidesSelect && Array.isArray(sides)) {
            sidesSelect.innerHTML = sides.map(s =>
                `<option value="${s.id}">${escapeHtml(s.name)}</option>`
            ).join('');
        }

        // Load ANALYST categories (FR-1.4): a dedicated namespace, fetched
        // from /api/analyst/categories - NEVER from /api/categories (which
        // serves the system "smart" taxonomy). These populate the analyst
        // filter and the manual-categorization bar only.
        await loadAnalystCategories();
    } catch (error) {
        console.error('Error loading filter options:', error);
    }
}

// Translate a key using the page-data translations (server-rendered) with an
// English fallback. Used by the analyst-categorization UI added in this page.
function tPage(key, fallback) {
    const pageDataEl = document.getElementById('search-advanced-page-data');
    if (pageDataEl) {
        try {
            const data = JSON.parse(pageDataEl.textContent);
            if (data.translations && data.translations[key]) {
                return data.translations[key];
            }
        } catch (e) { /* fall through */ }
    }
    return window.appTranslations?.[key] || fallback;
}

// Load analyst-defined categories into their own controls (FR-1.3, FR-1.4)
async function loadAnalystCategories() {
    try {
        const response = await fetch('/api/analyst/categories');
        if (!response.ok) return;
        const categories = await response.json();
        searchState.analystCategories = Array.isArray(categories) ? categories : [];

        // Advanced-filter multi-select (analyst namespace, separate control
        // from the "Smart Categories" select above)
        const filterSelect = document.getElementById('analystCategoriesFilter');
        if (filterSelect) {
            filterSelect.innerHTML = searchState.analystCategories.map(c =>
                `<option value="${c.id}">${escapeHtml(c.name)} (${c.file_count ?? 0})</option>`
            ).join('');
        }

        // Manual-categorization bar dropdown
        const barSelect = document.getElementById('analystCategorySelect');
        if (barSelect) {
            barSelect.innerHTML = '<option value="">' +
                escapeHtml(tPage('chooseOrCreateCategory', 'Choose analyst category…')) +
                '</option>' +
                searchState.analystCategories.map(c =>
                    `<option value="${c.id}">${escapeHtml(c.name)}</option>`
                ).join('');
        }
    } catch (error) {
        console.error('Error loading analyst categories:', error);
    }
}

// Load search suggestions
async function loadSearchSuggestions(query) {
    try {
        const response = await fetch(`/api/search/suggestions?query=${encodeURIComponent(query)}&limit=8`);
        const data = await response.json();
        
        if (data.suggestions && Array.isArray(data.suggestions)) {
            searchState.suggestions = data.suggestions;
            displaySuggestions(data.suggestions, query);
        }
    } catch (error) {
        console.error('Error loading suggestions:', error);
    }
}

// Display search suggestions
function displaySuggestions(suggestions, query) {
    const dropdown = document.getElementById('searchSuggestions');
    const list = document.getElementById('suggestionsList');
    
    if (!dropdown || !list) return;
    
    if (suggestions.length === 0) {
        hideSuggestions();
        return;
    }
    
    list.innerHTML = suggestions.map(suggestion => `
        <div class="suggestion-item" onclick="selectSuggestion('${suggestion.replace(/'/g, "\\'")}')">
            <i class="bi bi-search"></i>
            <span>${highlightMatch(suggestion, query)}</span>
        </div>
    `).join('');
    
    dropdown.classList.add('active');
}

// Highlight match in suggestion
function highlightMatch(text, query) {
    if (!query) return text;
    const regex = new RegExp(`(${query})`, 'gi');
    return text.replace(regex, '<mark>$1</mark>');
}

// Select suggestion
function selectSuggestion(suggestion) {
    document.getElementById('mainSearchInput').value = suggestion;
    searchState.query = suggestion;
    hideSuggestions();
    executeAdvancedSearch();
}

// Hide suggestions
function hideSuggestions() {
    const dropdown = document.getElementById('searchSuggestions');
    if (dropdown) {
        dropdown.classList.remove('active');
    }
}

// Update filter chips
function updateFilterChips() {
    const chips = [];
    
    // File types
    const fileTypes = Array.from(document.getElementById('fileType').selectedOptions).map(o => o.value);
    if (fileTypes.length > 0) {
        fileTypes.forEach(type => {
            if (type) chips.push({ type: 'fileType', label: 'File Type', value: type });
        });
    }
    
    // Categories (smart taxonomy - separate from analyst categories, FR-1.4)
    const categories = Array.from(document.getElementById('categoriesSelect').selectedOptions).map(o => o.value);
    if (categories.length > 0) {
        categories.forEach(catId => {
            const option = document.getElementById('categoriesSelect').querySelector(`option[value="${catId}"]`);
            if (option) {
                chips.push({ type: 'category', label: 'Smart Category', value: option.textContent, id: catId });
            }
        });
    }

    // Analyst categories (manual taxonomy - separate namespace, FR-1.4)
    const analystFilter = document.getElementById('analystCategoriesFilter');
    if (analystFilter) {
        Array.from(analystFilter.selectedOptions).forEach(opt => {
            chips.push({ type: 'analystCategory', label: 'Analyst Category', value: opt.textContent, id: opt.value });
        });
    }
    
    // Sources
    const sources = Array.from(document.getElementById('sourcesSelect').selectedOptions).map(o => o.value);
    if (sources.length > 0) {
        sources.forEach(sourceId => {
            const option = document.getElementById('sourcesSelect').querySelector(`option[value="${sourceId}"]`);
            if (option) {
                chips.push({ type: 'source', label: 'Source', value: option.textContent, id: sourceId });
            }
        });
    }
    
    // Sides
    const sides = Array.from(document.getElementById('sidesSelect').selectedOptions).map(o => o.value);
    if (sides.length > 0) {
        sides.forEach(sideId => {
            const option = document.getElementById('sidesSelect').querySelector(`option[value="${sideId}"]`);
            if (option) {
                chips.push({ type: 'side', label: 'Side', value: option.textContent, id: sideId });
            }
        });
    }
    
    // Date range
    const dateFrom = document.getElementById('dateFrom').value;
    const dateTo = document.getElementById('dateTo').value;
    if (dateFrom) {
        chips.push({ type: 'dateFrom', label: 'From', value: dateFrom });
    }
    if (dateTo) {
        chips.push({ type: 'dateTo', label: 'To', value: dateTo });
    }
    
    // Status
    const statusRead = document.getElementById('statusRead').checked;
    const statusUnread = document.getElementById('statusUnread').checked;
    if (statusRead && !statusUnread) {
        chips.push({ type: 'status', label: 'Status', value: 'Analyzed' });
    } else if (!statusRead && statusUnread) {
        chips.push({ type: 'status', label: 'Status', value: 'Pending' });
    }
    
    // Display chips
    displayFilterChips(chips);
    
    // Update active filters count
    const countEl = document.getElementById('activeFiltersCount');
    if (countEl) {
        countEl.textContent = chips.length;
    }
}

// Display filter chips
function displayFilterChips(chips) {
    const container = document.getElementById('filtersChipsContainer');
    const chipsEl = document.getElementById('filtersChips');
    
    if (!container || !chipsEl) return;
    
    if (chips.length === 0) {
        container.style.display = 'none';
        return;
    }
    
    container.style.display = 'block';
    chipsEl.innerHTML = chips.map((chip, index) => {
        const chipClass = chip.priority ? 'filter-chip priority-chip' : 'filter-chip';
        return `
            <div class="${chipClass}">
                <span class="chip-label">${chip.label}:</span>
                <span class="chip-value">${chip.value}</span>
                <button type="button" class="chip-remove" onclick="removeFilterChip(${index}, '${chip.type}', '${chip.id || ''}', ${chip.priority || false})">
                    <i class="bi bi-x"></i>
                </button>
            </div>
        `;
    }).join('');
}

// Remove filter chip
function removeFilterChip(index, type, id) {
    {
        // Handle regular filters
        switch (type) {
            case 'fileType':
                const fileTypeSelect = document.getElementById('fileType');
                const fileTypeOption = fileTypeSelect.querySelector(`option[value="${id}"]`);
                if (fileTypeOption) fileTypeOption.selected = false;
                break;
            case 'category':
                const categorySelect = document.getElementById('categoriesSelect');
                const categoryOption = categorySelect.querySelector(`option[value="${id}"]`);
                if (categoryOption) categoryOption.selected = false;
                break;
            case 'analystCategory':
                const analystFilter = document.getElementById('analystCategoriesFilter');
                if (analystFilter) {
                    const analystOption = analystFilter.querySelector(`option[value="${id}"]`);
                    if (analystOption) analystOption.selected = false;
                }
                break;
            case 'source':
                const sourceSelect = document.getElementById('sourcesSelect');
                const sourceOption = sourceSelect.querySelector(`option[value="${id}"]`);
                if (sourceOption) sourceOption.selected = false;
                break;
            case 'side':
                const sideSelect = document.getElementById('sidesSelect');
                const sideOption = sideSelect.querySelector(`option[value="${id}"]`);
                if (sideOption) sideOption.selected = false;
                break;
            case 'dateFrom':
                document.getElementById('dateFrom').value = '';
                break;
            case 'dateTo':
                document.getElementById('dateTo').value = '';
                break;
            case 'status':
                document.getElementById('statusRead').checked = true;
                document.getElementById('statusUnread').checked = false;
                break;
        }
    }
    updateFilterChips();
}

// Clear all filters
function clearAllFilters() {
    document.getElementById('fileType').selectedIndex = -1;
    document.getElementById('categoriesSelect').selectedIndex = -1;
    const analystFilter = document.getElementById('analystCategoriesFilter');
    if (analystFilter) analystFilter.selectedIndex = -1;
    document.getElementById('sourcesSelect').selectedIndex = -1;
    document.getElementById('sidesSelect').selectedIndex = -1;
    document.getElementById('dateFrom').value = '';
    document.getElementById('dateTo').value = '';
    document.getElementById('statusRead').checked = true;
    document.getElementById('statusUnread').checked = false;
    updateFilterChips();
}

// Toggle filters panel
function toggleFiltersPanel() {
    const content = document.getElementById('filtersPanelContent');
    const icon = document.getElementById('filtersToggleIcon');
    
    if (content && icon) {
        content.classList.toggle('active');
        icon.classList.toggle('bi-chevron-down');
        icon.classList.toggle('bi-chevron-up');
    }
}

// Execute advanced search
async function executeAdvancedSearch() {
    const startTime = performance.now();
    const query = document.getElementById('mainSearchInput').value.trim();
    
    if (!query && getActiveFiltersCount() === 0) {
        alert('Please enter a search query or select filters');
        return;
    }
    
    // Hide suggestions
    hideSuggestions();

    // A new search invalidates the previous result selection (FR-1.2)
    searchState.selectedIds = new Set();
    updateSelectionBar();

    // Show loading
    showLoading();
    
    // Collect filters. Source/side scoping lives in the advanced-filters
    // panel (the former "Search Within" block was merged into it).
    const sourceIds = Array.from(document.getElementById('sourcesSelect').selectedOptions).map(o => parseInt(o.value));
    const sideIds = Array.from(document.getElementById('sidesSelect').selectedOptions).map(o => parseInt(o.value));
    
    const filters = {
        file_type: Array.from(document.getElementById('fileType').selectedOptions).map(o => o.value).filter(v => v),
        category_id: Array.from(document.getElementById('categoriesSelect').selectedOptions).map(o => parseInt(o.value)),
        analyst_category_id: Array.from(document.getElementById('analystCategoriesFilter')?.selectedOptions || []).map(o => parseInt(o.value)).filter(v => !isNaN(v)),
        source_id: sourceIds.filter(id => !isNaN(id)),
        side_id: sideIds.filter(id => !isNaN(id)),
        date_from: document.getElementById('dateFrom').value || null,
        date_to: document.getElementById('dateTo').value || null,
        status: []
    };
    
    if (document.getElementById('statusRead').checked) filters.status.push('Read');
    if (document.getElementById('statusUnread').checked) filters.status.push('Unread');
    
    // Show warning if searching without source/side filter (for large databases)
    if (!filters.source_id.length && !filters.side_id.length && !query) {
        const confirmSearch = confirm(tPage('largeSearchConfirm',
            'Searching without a source or side filter may be slow on large datasets. Continue?'));
        if (!confirmSearch) return;
    }
    
    // Search options
    const options = {
        case_sensitive: document.getElementById('caseSensitive').checked,
        whole_word: document.getElementById('wholeWord').checked,
        use_fuzzy: document.getElementById('useFuzzy').checked
    };
    
    try {
        // Use advanced search API
        const params = new URLSearchParams({
            query: query || '',
            page: searchState.currentPage,
            per_page: searchState.resultsPerPage,
            use_advanced: 'true',
            use_bm25: 'true',
            use_expansion: 'true',
            use_fuzzy: options.use_fuzzy ? 'true' : 'false',
            sort_by: document.getElementById('sortBy').value || 'relevance',
            sort_order: 'desc'
        });

        // Analyst-categorization search scope (FR-2.x). Always sent so the
        // server can persist the selection in the session (FR-2.3) and apply
        // the default "uncategorized only" behavior (FR-2.1).
        params.set('scope', searchState.scope);

        // Add filters
        if (filters.file_type.length > 0) {
            filters.file_type.forEach(type => params.append('file_type', type));
        }
        if (filters.category_id.length > 0) {
            filters.category_id.forEach(id => params.append('category_id', id));
        }
        // Analyst-category filter - a separate parameter from the smart
        // category_id filter above (FR-1.4 separation).
        if (filters.analyst_category_id.length > 0) {
            filters.analyst_category_id.forEach(id => params.append('analyst_category_id', id));
        }
        if (filters.source_id.length > 0) {
            filters.source_id.forEach(id => params.append('source_id', id));
        }
        if (filters.side_id.length > 0) {
            filters.side_id.forEach(id => params.append('side_id', id));
        }
        if (filters.date_from) params.append('date_from', filters.date_from);
        if (filters.date_to) params.append('date_to', filters.date_to);
        
        const response = await fetch(`/api/search?${params.toString()}`);
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        const data = await response.json();
        
        const endTime = performance.now();
        searchState.searchTime = ((endTime - startTime) / 1000).toFixed(2);
        
        // Process results
        if (data.results && Array.isArray(data.results)) {
            searchState.results = data.results;
            searchState.totalResults = data.pagination?.total || data.results.length;
            displayResults(data.results, data.pagination);
        } else {
            searchState.results = [];
            searchState.totalResults = 0;
            displayResults([], null);
        }
        
        // Note: Search history is already saved by the API endpoint
        // This is a backup save (optional, won't cause errors if it fails)
        if (query) {
            // Only save if API didn't already save it (check response)
            // For now, skip to avoid duplicate saves - API already handles it
            // saveToSearchHistory(query, filters);
        }
        
    } catch (error) {
        console.error('Search error:', error);
        alert(tPage('searchError', 'Search error') + ': ' + error.message);
        searchState.results = [];
        displayResults([], null);
    } finally {
        hideLoading();
    }
}

// File-type presentation metadata: bootstrap icon + color-tint CSS class
// shared by the result icon and the type chip.
function fileTypeMeta(type) {
    const map = {
        pdf:          { icon: 'bi-filetype-pdf',  css: 'type-pdf' },
        doc:          { icon: 'bi-filetype-doc',  css: 'type-doc' },
        docx:         { icon: 'bi-filetype-docx', css: 'type-docx' },
        xls:          { icon: 'bi-filetype-xlsx', css: 'type-xls' },
        xlsx:         { icon: 'bi-filetype-xlsx', css: 'type-xlsx' },
        csv:          { icon: 'bi-filetype-csv',  css: 'type-xls' },
        ppt:          { icon: 'bi-filetype-pptx', css: 'type-ppt' },
        pptx:         { icon: 'bi-filetype-pptx', css: 'type-pptx' },
        txt:          { icon: 'bi-filetype-txt',  css: 'type-txt' },
        md:           { icon: 'bi-filetype-md',   css: 'type-txt' },
        html:         { icon: 'bi-filetype-html', css: 'type-code' },
        htm:          { icon: 'bi-filetype-html', css: 'type-code' },
        json:         { icon: 'bi-filetype-json', css: 'type-code' },
        xml:          { icon: 'bi-filetype-xml',  css: 'type-code' },
        js:           { icon: 'bi-filetype-js',   css: 'type-code' },
        py:           { icon: 'bi-filetype-py',   css: 'type-code' },
        jpg:          { icon: 'bi-filetype-jpg',  css: 'type-img' },
        jpeg:         { icon: 'bi-filetype-jpg',  css: 'type-img' },
        png:          { icon: 'bi-filetype-png',  css: 'type-img' },
        gif:          { icon: 'bi-filetype-gif',  css: 'type-img' },
        bmp:          { icon: 'bi-filetype-bmp',  css: 'type-img' },
        webp:         { icon: 'bi-filetype-png',  css: 'type-img' },
        tif:          { icon: 'bi-filetype-tiff', css: 'type-img' },
        tiff:         { icon: 'bi-filetype-tiff', css: 'type-img' },
        mp3:          { icon: 'bi-filetype-mp3',  css: 'type-audio' },
        wav:          { icon: 'bi-filetype-wav',  css: 'type-audio' },
        m4a:          { icon: 'bi-filetype-mp3',  css: 'type-audio' },
        mp4:          { icon: 'bi-filetype-mp4',  css: 'type-video' },
        avi:          { icon: 'bi-filetype-avi',  css: 'type-video' },
        mkv:          { icon: 'bi-filetype-mkv',  css: 'type-video' },
        mov:          { icon: 'bi-filetype-mov',  css: 'type-video' },
        zip:          { icon: 'bi-filetype-zip',  css: 'type-archive' },
        rar:          { icon: 'bi-filetype-rar',  css: 'type-archive' },
        '7z':         { icon: 'bi-filetype-7z',   css: 'type-archive' },
        gz:           { icon: 'bi-filetype-zip',  css: 'type-archive' },
        eml:          { icon: 'bi-envelope',      css: 'type-email' },
        msg:          { icon: 'bi-envelope',      css: 'type-email' },
        email:        { icon: 'bi-envelope',      css: 'type-email' },
    };
    return map[type] || { icon: 'bi-file-earmark', css: '' };
}

// Display results
function displayResults(results, pagination) {
    const section = document.getElementById('searchResultsSection');
    const container = document.getElementById('resultsContainer');
    const countEl = document.getElementById('resultsCount');
    const timeEl = document.getElementById('searchTime');
    
    if (!section || !container) return;
    
    section.style.display = 'block';
    
    if (countEl) {
        countEl.textContent = searchState.totalResults.toLocaleString();
    }
    
    if (timeEl) {
        const pageDataEl = document.getElementById('search-advanced-page-data');
        let timeText = `in ${searchState.searchTime} seconds`;
        if (pageDataEl) {
            try {
                const data = JSON.parse(pageDataEl.textContent);
                timeText = data.translations?.inSeconds?.replace('{seconds}', searchState.searchTime) || timeText;
            } catch (e) {}
        }
        timeEl.textContent = timeText;
    }
    
    if (results.length === 0) {
        container.innerHTML = `
            <div class="results-empty-state">
                <i class="bi bi-search" aria-hidden="true"></i>
                <p>${escapeHtml(tPage('noResultsFound', 'No results found matching your criteria'))}</p>
            </div>
        `;
        return;
    }
    
    container.innerHTML = results.map(result => {
        const snippet = result.snippet || result.file_name || '';
        const highlightedSnippet = highlightQueryTerms(snippet, searchState.query);

        // File-type presentation: color-coded icon + uppercase chip share
        // one tint family per type (see search-advanced.css .type-*).
        const fileType = (result.file_type || '').toLowerCase();
        const typeInfo = fileTypeMeta(fileType);

        // Analyst categories (manual layer) - always rendered in their own,
        // visually distinct badge group, never merged with smart categories
        // (FR-1.4).
        const analystBadges = (result.analyst_categories || []).length > 0 ? `
            <span class="analyst-badges" title="${escapeAttr(tPage('analystCategories', 'Analyst'))}">
                ${(result.analyst_categories || []).map(cat =>
                    `<span class="badge analyst-category-badge"><i class="bi bi-person-fill me-1"></i>${escapeHtml(cat)}</span>`
                ).join('')}
            </span>
        ` : '';

        // Smart categories (system layer) - separate badge group
        const smartBadges = result.categories && result.categories.length > 0 ? `
            <span class="smart-badges" title="${escapeAttr(tPage('smartCategories', 'Smart'))}">
                ${result.categories.map(cat => `<span class="badge bg-secondary"><i class="bi bi-tags-fill me-1"></i>${escapeHtml(cat)}</span>`).join('')}
            </span>
        ` : '';

        return `
            <div class="result-item ${searchState.selectedIds.has(result.id) ? 'result-selected' : ''}" data-file-id="${result.id}">
                <div class="result-select" onclick="event.stopPropagation()">
                    <input class="form-check-input result-checkbox" type="checkbox"
                           ${searchState.selectedIds.has(result.id) ? 'checked' : ''}
                           onchange="toggleResultSelection(${result.id}, this.checked)"
                           title="${escapeAttr(tPage('selectForCategorization', 'Select for manual categorization'))}"
                           aria-label="${escapeAttr(tPage('selectFileForCategorization', 'Select {file} for manual categorization').replace('{file}', result.file_name || 'file'))}">
                </div>
                <div class="result-body" onclick="window.location.href='${fileDetailHref(result.id)}'">
                    <div class="result-title-row">
                        <span class="result-file-icon ${typeInfo.css}" title="${escapeAttr(fileType || '')}">
                            <i class="bi ${typeInfo.icon}" aria-hidden="true"></i>
                        </span>
                        <span class="result-title">${escapeHtml(result.file_name || tPage('untitled', 'Untitled'))}</span>
                        ${fileType ? `<span class="result-type-chip ${typeInfo.css}">${escapeHtml(fileType)}</span>` : ''}
                        ${result.relevance_score ? `<span class="relevance-badge">${Math.round(result.relevance_score * 100)}%</span>` : ''}
                    </div>
                    ${snippet ? `<div class="result-snippet">${highlightedSnippet}</div>` : ''}
                    <div class="result-meta">
                        <span class="result-meta-item">
                            <i class="bi bi-building" aria-hidden="true"></i>
                            ${escapeHtml(result.source_name || tPage('unknown', 'unknown'))}
                        </span>
                        <span class="result-meta-item">
                            <i class="bi bi-calendar" aria-hidden="true"></i>
                            ${result.file_date ? new Date(result.file_date).toLocaleDateString() : tPage('notAvailable', 'N/A')}
                        </span>
                        ${result.file_size ? `
                            <span class="result-meta-item">
                                <i class="bi bi-hdd" aria-hidden="true"></i>
                                ${formatFileSize(result.file_size)}
                            </span>
                        ` : ''}
                    </div>
                    ${(analystBadges || smartBadges) ? `
                        <div class="result-badges">
                            ${analystBadges}
                            ${smartBadges}
                        </div>
                    ` : ''}
                </div>
            </div>
        `;
    }).join('');

    // Sync the select-all checkbox with the fresh result page
    syncSelectAllCheckbox();
    
    // Update pagination
    if (pagination && pagination.total_pages > 1) {
        updatePagination(pagination);
    } else {
        const paginationEl = document.getElementById('pagination');
        if (paginationEl) paginationEl.innerHTML = '';
    }
}

// ====================================================================
// Analyst-driven manual categorization (FR-1.2, FR-1.3, FR-1.5)
// All actions below target ANALYST categories only - the smart
// (system-generated) taxonomy is never read or written here (FR-1.4).
// ====================================================================

// Toggle one result's selection checkbox (FR-1.2 - subset selection)
function toggleResultSelection(fileId, checked) {
    if (checked) {
        searchState.selectedIds.add(fileId);
    } else {
        searchState.selectedIds.delete(fileId);
    }
    const item = document.querySelector(`.result-item[data-file-id="${fileId}"]`);
    if (item) item.classList.toggle('result-selected', checked);
    syncSelectAllCheckbox();
    updateSelectionBar();
}

// Select/deselect every result on the current page (FR-1.2 - select all)
function toggleSelectAllResults(checked) {
    searchState.results.forEach(result => {
        if (checked) {
            searchState.selectedIds.add(result.id);
        } else {
            searchState.selectedIds.delete(result.id);
        }
        const checkbox = document.querySelector(
            `.result-item[data-file-id="${result.id}"] .result-checkbox`);
        if (checkbox) checkbox.checked = checked;
        const item = document.querySelector(`.result-item[data-file-id="${result.id}"]`);
        if (item) item.classList.toggle('result-selected', checked);
    });
    updateSelectionBar();
}

// Keep the select-all checkbox in sync with the visible page
function syncSelectAllCheckbox() {
    const selectAll = document.getElementById('selectAllResults');
    if (!selectAll || searchState.results.length === 0) return;
    const allSelected = searchState.results.every(r => searchState.selectedIds.has(r.id));
    const someSelected = searchState.results.some(r => searchState.selectedIds.has(r.id));
    selectAll.checked = allSelected;
    selectAll.indeterminate = !allSelected && someSelected;
}

// Show/hide the categorization bar and update its counters
function updateSelectionBar() {
    const bar = document.getElementById('analystCategorizationBar');
    if (!bar) return;
    const count = searchState.selectedIds.size;
    const countEl = document.getElementById('analystSelectedCount');
    if (countEl) countEl.textContent = count;
    bar.style.display = count > 0 && searchState.canCategorize ? 'flex' : 'none';
}

// Clear the current selection
function clearResultSelection() {
    searchState.selectedIds.clear();
    document.querySelectorAll('.result-checkbox').forEach(cb => cb.checked = false);
    document.querySelectorAll('.result-item.result-selected').forEach(el =>
        el.classList.remove('result-selected'));
    syncSelectAllCheckbox();
    updateSelectionBar();
}

// CSRF header helper for the categorization POSTs
function analystCsrftoken() {
    return document.querySelector('meta[name="csrf-token"]')?.getAttribute('content') || '';
}

// Assign the chosen analyst category to every selected file (FR-1.3).
// The current search query travels with the request so each assignment is
// auditable with its originating query (FR-1.5).
async function assignAnalystCategory() {
    if (!searchState.canCategorize) return;
    const selected = Array.from(searchState.selectedIds);
    if (selected.length === 0) {
        alert(tPage('selectFilesFirst', 'Select one or more files first'));
        return;
    }

    const categorySelect = document.getElementById('analystCategorySelect');
    const newCategoryInput = document.getElementById('newAnalystCategoryInput');
    const categoryId = categorySelect ? parseInt(categorySelect.value) : NaN;
    const newCategoryName = newCategoryInput ? newCategoryInput.value.trim() : '';

    if (!newCategoryName && (isNaN(categoryId) || !categoryId)) {
        alert(tPage('chooseOrCreateCategory', 'Choose an analyst category or type a new one'));
        return;
    }

    const payload = {
        path_ids: selected,
        source_query: searchState.query || document.getElementById('mainSearchInput')?.value?.trim() || ''
    };
    if (newCategoryName) {
        // Create the analyst-defined category at the point of assignment
        payload.category_name = newCategoryName;
        payload.create_category = true;
    } else {
        payload.category_id = categoryId;
    }

    try {
        const response = await fetch('/api/analyst/assign', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': analystCsrftoken()
            },
            body: JSON.stringify(payload)
        });
        const data = await response.json();
        if (!response.ok || !data.success) {
            throw new Error(data.error || 'Request failed');
        }

        // Update the in-memory results so the analyst badges reflect the
        // action immediately (and the scope hint stays honest).
        const categoryName = data.category_name || newCategoryName;
        searchState.results.forEach(result => {
            if (searchState.selectedIds.has(result.id)) {
                result.analyst_categories = result.analyst_categories || [];
                if (categoryName && !result.analyst_categories.includes(categoryName)) {
                    result.analyst_categories.push(categoryName);
                }
            }
        });
        displayResults(searchState.results, {
            total_pages: Math.ceil(searchState.totalResults / searchState.resultsPerPage) || 1
        });

        if (newCategoryInput) newCategoryInput.value = '';
        if (categorySelect) categorySelect.value = '';
        // Refresh the analyst category lists (a new category may exist now)
        await loadAnalystCategories();

        showAnalystToast(
            tPage('assignedToast', 'Assigned "{category}" to {count} file(s)')
                .replace('{category}', categoryName)
                .replace('{count}', String(data.assigned ?? selected.length))
        );
        // The assignment was audit-logged server-side (FR-1.5).
        clearResultSelection();
    } catch (error) {
        console.error('Analyst categorization failed:', error);
        alert(tPage('analystActionError', 'Analyst categorization failed') + ': ' + error.message);
    }
}

// Remove analyst categories from the selected files (NFR-3 - reversibility).
// Only the manual layer is touched; smart categories are never modified.
async function removeAnalystCategoriesFromSelection() {
    if (!searchState.canCategorize) return;
    const selected = Array.from(searchState.selectedIds);
    if (selected.length === 0) {
        alert(tPage('selectFilesFirst', 'Select one or more files first'));
        return;
    }

    const confirmed = confirm(
        tPage('removeAllConfirm', 'Remove all analyst categories from {count} selected file(s)? They will return to "uncategorized" for analyst search scope. Smart categories are not affected.')
            .replace('{count}', String(selected.length)));
    if (!confirmed) return;

    try {
        const response = await fetch('/api/analyst/remove', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': analystCsrftoken()
            },
            body: JSON.stringify({
                path_ids: selected,
                source_query: searchState.query || ''
            })
        });
        const data = await response.json();
        if (!response.ok || !data.success) {
            throw new Error(data.error || 'Request failed');
        }

        searchState.results.forEach(result => {
            if (searchState.selectedIds.has(result.id)) {
                result.analyst_categories = [];
            }
        });
        displayResults(searchState.results, {
            total_pages: Math.ceil(searchState.totalResults / searchState.resultsPerPage) || 1
        });

        showAnalystToast(tPage('analystRemoveSuccess', 'Analyst categories removed'));
        clearResultSelection();
    } catch (error) {
        console.error('Analyst category removal failed:', error);
        alert(tPage('analystActionError', 'Analyst categorization failed') + ': ' + error.message);
    }
}

// Lightweight toast for categorization feedback
function showAnalystToast(message) {
    let toast = document.getElementById('analystActionToast');
    if (!toast) {
        toast = document.createElement('div');
        toast.id = 'analystActionToast';
        toast.className = 'analyst-action-toast';
        document.body.appendChild(toast);
    }
    toast.textContent = message;
    toast.classList.add('visible');
    clearTimeout(toast._hideTimer);
    toast._hideTimer = setTimeout(() => toast.classList.remove('visible'), 4000);
}

// Highlight query terms in text
function highlightQueryTerms(text, query) {
    if (!query || !text) return text;
    
    // Parse query for terms (handle quotes, AND, OR, NOT)
    const terms = parseQueryTerms(query);
    
    let highlighted = text;
    terms.forEach(term => {
        const regex = new RegExp(`(${term.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')})`, 'gi');
        highlighted = highlighted.replace(regex, '<mark>$1</mark>');
    });
    
    return highlighted;
}

// Parse query terms (handle quotes, operators)
function parseQueryTerms(query) {
    const terms = [];
    const quoted = query.match(/"([^"]+)"/g);
    const unquoted = query.replace(/"([^"]+)"/g, '').trim();
    
    if (quoted) {
        quoted.forEach(q => terms.push(q.replace(/"/g, '')));
    }
    
    if (unquoted) {
        unquoted.split(/\s+(?:AND|OR|NOT)\s+/i).forEach(term => {
            const cleanTerm = term.trim().replace(/\b(AND|OR|NOT)\b/gi, '').trim();
            if (cleanTerm) terms.push(cleanTerm);
        });
    }
    
    return terms.length > 0 ? terms : [query];
}

// Update pagination
function updatePagination(pagination) {
    const paginationEl = document.getElementById('pagination');
    if (!paginationEl) return;
    
    import('../modules/rendering/unified-pagination.js').then(module => {
        module.renderUnifiedPagination({
            currentPage: pagination.page,
            totalPages: pagination.total_pages,
            containerId: 'pagination',
            onPageChange: (page) => {
                searchState.currentPage = page;
                executeAdvancedSearch();
            },
            urlParams: {},
            showInfo: true,
            showJump: pagination.total_pages > 5
        });
    }).catch(err => {
        console.error('Error loading pagination:', err);
    });
}

// Show loading
function showLoading() {
    const overlay = document.getElementById('searchLoadingOverlay');
    if (overlay) overlay.style.display = 'flex';
}

// Hide loading
function hideLoading() {
    const overlay = document.getElementById('searchLoadingOverlay');
    if (overlay) overlay.style.display = 'none';
}

// Get active filters count
function getActiveFiltersCount() {
    let count = 0;
    count += document.getElementById('fileType').selectedOptions.length;
    count += document.getElementById('categoriesSelect').selectedOptions.length;
    count += document.getElementById('sourcesSelect').selectedOptions.length;
    count += document.getElementById('sidesSelect').selectedOptions.length;
    if (document.getElementById('dateFrom').value) count++;
    if (document.getElementById('dateTo').value) count++;
    if (!document.getElementById('statusRead').checked || document.getElementById('statusUnread').checked) count++;
    return count;
}

// Reset all filters
function resetAllFilters() {
    document.getElementById('mainSearchInput').value = '';
    searchState.query = '';
    clearAllFilters();
    document.getElementById('caseSensitive').checked = false;
    document.getElementById('wholeWord').checked = false;
    document.getElementById('useFuzzy').checked = true;
    document.getElementById('searchResultsSection').style.display = 'none';
    updateFilterChips();
}

// Feeling lucky (get first result)
async function feelingLucky() {
    searchState.resultsPerPage = 1;
    await executeAdvancedSearch();
    if (searchState.results.length > 0) {
        window.location.href = `/file/${searchState.results[0].id}`;
    }
    searchState.resultsPerPage = 20;
}

// Load search history
async function loadSearchHistory() {
    try {
        const response = await fetch('/api/search/history?limit=10');
        const data = await response.json();
        if (data.history) {
            searchState.searchHistory = data.history;
        }
    } catch (error) {
        console.error('Error loading search history:', error);
    }
}

// Save to search history
async function saveToSearchHistory(query, filters) {
    if (!query || !query.trim()) return; // Don't save empty queries
    
    try {
        const response = await fetch('/api/search/history', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ 
                query: query.trim(),
                filters: filters || {},
                result_count: searchState.totalResults || 0
            })
        });
        
        if (!response.ok) {
            // Don't show error to user, just log it
            const errorData = await response.json().catch(() => ({}));
            console.warn('Could not save search history:', errorData.error || 'Unknown error');
        }
    } catch (error) {
        // Silently fail - history saving is not critical
        console.warn('Error saving search history:', error);
    }
}

// Sort results
function sortResults() {
    const sortBy = document.getElementById('sortBy').value;
    searchState.currentPage = 1;
    executeAdvancedSearch();
}

// Export results in various formats
function exportResults(format = 'csv') {
    if (searchState.results.length === 0) {
        alert('No results to export');
        return;
    }
    
    const timestamp = new Date().toISOString().split('T')[0];
    const query = document.getElementById('mainSearchInput')?.value || 'search';
    
    switch (format) {
        case 'csv':
            exportAsCSV(timestamp, query);
            break;
        case 'excel':
            exportAsExcel(timestamp, query);
            break;
        case 'json':
            exportAsJSON(timestamp, query);
            break;
        default:
            exportAsCSV(timestamp, query);
    }
}

// Export as CSV with all details
function exportAsCSV(timestamp, query) {
    // CSV header with all available fields
    const headers = [
        'File ID',
        'File Name',
        'File Path',
        'File Type',
        'File Size (bytes)',
        'File Size (formatted)',
        'File Date',
        'File Status',
        'Source Name',
        'Source ID',
        'Side Name',
        'Side ID',
        'Relevance Score',
        'Categories',
        'Date Created',
        'Snippet'
    ];
    
    const csvRows = [headers.join(',')];
    
    searchState.results.forEach(result => {
        const row = [
            escapeCSV(result.id || ''),
            escapeCSV(result.file_name || ''),
            escapeCSV(result.file_path || ''),
            escapeCSV(result.file_type || ''),
            result.file_size || 0,
            escapeCSV(formatFileSize(result.file_size || 0)),
            escapeCSV(result.file_date ? new Date(result.file_date).toLocaleDateString() : ''),
            escapeCSV(result.file_status || ''),
            escapeCSV(result.source_name || ''),
            result.source_id || '',
            escapeCSV(result.side_name || ''),
            result.side_id || '',
            (result.relevance_score || 0).toFixed(2),
            escapeCSV(Array.isArray(result.categories) ? result.categories.join('; ') : ''),
            escapeCSV(result.date_creation ? new Date(result.date_creation).toLocaleDateString() : ''),
            escapeCSV(result.snippet || '')
        ];
        csvRows.push(row.join(','));
    });
    
    const csv = csvRows.join('\n');
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
    downloadBlob(blob, `search_results_${sanitizeFilename(query)}_${timestamp}.csv`);
}

// Export as Excel (CSV format with .xlsx extension, or use a library)
function exportAsExcel(timestamp, query) {
    // For now, export as CSV with Excel-compatible format
    // In production, you might want to use a library like SheetJS
    exportAsCSV(timestamp, query);
    
    // Alternative: Use server-side Excel generation
    // fetch('/api/search/export', {
    //     method: 'POST',
    //     headers: { 'Content-Type': 'application/json' },
    //     body: JSON.stringify({ results: searchState.results, format: 'excel' })
    // }).then(response => response.blob())
    //   .then(blob => downloadBlob(blob, `search_results_${query}_${timestamp}.xlsx`));
}

// Export as JSON
function exportAsJSON(timestamp, query) {
    const exportData = {
        query: query,
        timestamp: new Date().toISOString(),
        total_results: searchState.totalResults,
        search_time: searchState.searchTime,
        filters: {
            source_id: Array.from(document.getElementById('sourcesSelect')?.selectedOptions || []).map(o => parseInt(o.value)),
            side_id: Array.from(document.getElementById('sidesSelect')?.selectedOptions || []).map(o => parseInt(o.value)),
            categories: Array.from(document.getElementById('categoriesSelect')?.selectedOptions || []).map(o => parseInt(o.value)),
            file_type: Array.from(document.getElementById('fileType')?.selectedOptions || []).map(o => o.value),
            date_from: document.getElementById('dateFrom')?.value || null,
            date_to: document.getElementById('dateTo')?.value || null
        },
        results: searchState.results.map(result => ({
            id: result.id,
            file_name: result.file_name,
            file_path: result.file_path,
            file_type: result.file_type,
            file_size: result.file_size,
            file_size_formatted: formatFileSize(result.file_size || 0),
            file_date: result.file_date,
            file_status: result.file_status,
            source_name: result.source_name,
            source_id: result.source_id,
            side_name: result.side_name,
            side_id: result.side_id,
            relevance_score: result.relevance_score,
            categories: result.categories || [],
            date_creation: result.date_creation,
            snippet: result.snippet
        }))
    };
    
    const json = JSON.stringify(exportData, null, 2);
    const blob = new Blob([json], { type: 'application/json;charset=utf-8;' });
    downloadBlob(blob, `search_results_${sanitizeFilename(query)}_${timestamp}.json`);
}

// Print results
function printResults() {
    if (searchState.results.length === 0) {
        alert('No results to print');
        return;
    }
    
    const query = document.getElementById('mainSearchInput')?.value || 'Search Results';
    const printWindow = window.open('', '_blank');
    
    const printContent = `
<!DOCTYPE html>
<html>
<head>
    <title>Search Results - ${query}</title>
    <style>
        @media print {
            @page { margin: 1cm; }
            body { font-family: Arial, sans-serif; font-size: 10pt; }
            h1 { font-size: 18pt; margin-bottom: 10pt; }
            h2 { font-size: 14pt; margin-top: 15pt; margin-bottom: 8pt; }
            table { width: 100%; border-collapse: collapse; margin-top: 10pt; }
            th, td { border: 1px solid #ddd; padding: 6pt; text-align: left; }
            th { background-color: #f2f2f2; font-weight: bold; }
            tr:nth-child(even) { background-color: #f9f9f9; }
            .header-info { margin-bottom: 15pt; }
            .header-info p { margin: 3pt 0; }
            .no-print { display: none; }
        }
        body { font-family: Arial, sans-serif; font-size: 10pt; padding: 20px; }
        h1 { font-size: 18pt; margin-bottom: 10pt; }
        h2 { font-size: 14pt; margin-top: 15pt; margin-bottom: 8pt; }
        table { width: 100%; border-collapse: collapse; margin-top: 10pt; }
        th, td { border: 1px solid #ddd; padding: 6pt; text-align: left; }
        th { background-color: #f2f2f2; font-weight: bold; }
        tr:nth-child(even) { background-color: #f9f9f9; }
        .header-info { margin-bottom: 15pt; }
        .header-info p { margin: 3pt 0; }
    </style>
</head>
<body>
    <h1>Search Results: ${escapeHtml(query)}</h1>
    <div class="header-info">
        <p><strong>Total Results:</strong> ${searchState.totalResults.toLocaleString()}</p>
        <p><strong>Search Time:</strong> ${searchState.searchTime} seconds</p>
        <p><strong>Date:</strong> ${new Date().toLocaleString()}</p>
    </div>
    <table>
        <thead>
            <tr>
                <th>#</th>
                <th>File Name</th>
                <th>File Path</th>
                <th>Type</th>
                <th>Size</th>
                <th>Date</th>
                <th>Source</th>
                <th>Side</th>
                <th>Relevance</th>
            </tr>
        </thead>
        <tbody>
            ${searchState.results.map((result, index) => `
                <tr>
                    <td>${index + 1}</td>
                    <td>${escapeHtml(result.file_name || 'N/A')}</td>
                    <td>${escapeHtml(result.file_path || 'N/A')}</td>
                    <td>${escapeHtml(result.file_type || 'N/A')}</td>
                    <td>${formatFileSize(result.file_size || 0)}</td>
                    <td>${result.file_date ? new Date(result.file_date).toLocaleDateString() : 'N/A'}</td>
                    <td>${escapeHtml(result.source_name || 'N/A')}</td>
                    <td>${escapeHtml(result.side_name || 'N/A')}</td>
                    <td>${result.relevance_score ? (result.relevance_score * 100).toFixed(1) + '%' : 'N/A'}</td>
                </tr>
            `).join('')}
        </tbody>
    </table>
    <script>
        window.onload = function() {
            window.print();
        };
    </script>
</body>
</html>`;
    
    printWindow.document.write(printContent);
    printWindow.document.close();
}

// Helper function to escape CSV values
function escapeCSV(value) {
    if (value === null || value === undefined) return '""';
    const stringValue = String(value);
    if (stringValue.includes(',') || stringValue.includes('"') || stringValue.includes('\n')) {
        return `"${stringValue.replace(/"/g, '""')}"`;
    }
    return stringValue;
}

// Helper function to escape HTML
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// Attribute-context escaper: escapeHtml (innerHTML text serialization)
// leaves quotes intact, which would let a crafted filename break out of
// title="/aria-label=" attributes. This escapes quotes as well.
function escapeAttr(text) {
    return String(text == null ? '' : text)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

// Helper function to download blob
function downloadBlob(blob, filename) {
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    window.URL.revokeObjectURL(url);
}

// Format file size (keep for backward compatibility)
function formatFileSize(bytes) {
    if (!bytes || bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return Math.round((bytes / Math.pow(k, i)) * 100) / 100 + ' ' + sizes[i];
}

// Helper function to sanitize filename
function sanitizeFilename(filename) {
    return filename.replace(/[^a-z0-9]/gi, '_').toLowerCase().substring(0, 50);
}

// Expose functions globally
if (typeof window !== 'undefined') {
    window.executeAdvancedSearch = executeAdvancedSearch;
    window.resetAllFilters = resetAllFilters;
    window.clearAllFilters = clearAllFilters;
    window.toggleFiltersPanel = toggleFiltersPanel;
    window.removeFilterChip = removeFilterChip;
    window.selectSuggestion = selectSuggestion;
    window.feelingLucky = feelingLucky;
    window.sortResults = sortResults;
    window.exportResults = exportResults;
    window.printResults = printResults;
    // Analyst manual-categorization actions (FR-1.2 / FR-1.3 / NFR-3)
    window.toggleResultSelection = toggleResultSelection;
    window.toggleSelectAllResults = toggleSelectAllResults;
    window.clearResultSelection = clearResultSelection;
    window.assignAnalystCategory = assignAnalystCategory;
    window.removeAnalystCategoriesFromSelection = removeAnalystCategoriesFromSelection;
    console.log('Advanced Search functions exposed globally');
}
