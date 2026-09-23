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

let activeAdvancedSearchController = null;
let advancedSearchRequestSequence = 0;

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
    lastDefinition: null,
    currentPage: 1,
    resultsPerPage: 20,
    totalResults: 0,
    searchTime: 0,
    suggestions: [],
    searchHistory: []
};

async function initializeSearchAdvancedPage() {
    console.log('Advanced Search page loaded - Google-like implementation');
    initializePageData();
    initializeSearch();
    initializeScopeSelector();
    setupEventListeners();

    // History is independent of filter controls; load it without delaying the
    // initial search. URL/saved-search restoration must wait until every
    // asynchronous select has its options, or selected IDs are silently lost.
    void loadSearchHistory();
    await loadFilterOptions();
    restoreSearchFromUrlAndRun();
    window.addEventListener('popstate', restoreSearchFromUrlAndRun);
}

export default function init() {
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initializeSearchAdvancedPage, { once: true });
    } else {
        initializeSearchAdvancedPage();
    }
}

// ====================================================================
// Search-state persistence (the "search is lost" fix, part 1)
// ---------------------------------------------------------------------
// The complete search definition — query, analyst scope, filters,
// match options, sort and page — is serialized into the page URL after
// every search (history.replaceState, no history spam) and restored
// from the URL on load. A refresh, a return to this tab, or a shared
// link therefore reproduces the exact result list.
//
// The same definition object is what "Save search" stores, and the
// same parameter encoding is mirrored server-side in
// Api/routes/search.py (_advanced_search_run_url) so saved searches
// from the management page land here fully restored.
// ====================================================================

// URL parameters understood by restoreSearchFromUrl(). Keep in sync
// with _advanced_search_run_url in Api/routes/search.py.
const SEARCH_URL_PARAMS = ['q', 'scope', 'sort', 'cs', 'ww', 'fz', 'ft',
    'cat', 'acat', 'src', 'side', 'df', 'dt', 'st', 'page'];

/** The search exactly as the on-screen controls currently define it. */
function currentSearchDefinition() {
    return {
        query: document.getElementById('mainSearchInput')?.value?.trim() || '',
        scope: searchState.scope,
        sort_by: document.getElementById('sortBy')?.value || 'relevance',
        page: searchState.currentPage,
        options: {
            case_sensitive: document.getElementById('caseSensitive')?.checked || false,
            whole_word: document.getElementById('wholeWord')?.checked || false,
            use_fuzzy: document.getElementById('useFuzzy')?.checked !== false
        },
        filters: collectFilters()
    };
}

/** Encode a search definition into URL parameters (lossless). */
function serializeDefinitionToParams(def) {
    const params = new URLSearchParams();
    const filters = def.filters || {};
    const options = def.options || {};

    if (def.query) params.set('q', def.query);
    if (def.scope && def.scope !== 'uncategorized') params.set('scope', def.scope);
    if (def.sort_by && def.sort_by !== 'relevance') params.set('sort', def.sort_by);
    if (options.case_sensitive) params.set('cs', '1');
    if (options.whole_word) params.set('ww', '1');
    if (options.use_fuzzy === false) params.set('fz', '0');

    const appendAll = (key, values) =>
        (values || []).forEach(v => params.append(key, String(v)));
    appendAll('ft', filters.file_type);
    appendAll('cat', filters.category_id);
    appendAll('acat', filters.analyst_category_id);
    appendAll('src', filters.source_id);
    appendAll('side', filters.side_id);

    if (filters.date_from) params.set('df', filters.date_from);
    if (filters.date_to) params.set('dt', filters.date_to);

    const status = Array.isArray(filters.status) ? filters.status : ['Read'];
    const read = status.includes('Read');
    const unread = status.includes('Unread');
    if (read && unread) params.set('st', 'read,unread');
    else if (!read && unread) params.set('st', 'unread');
    else if (!read && !unread) params.set('st', 'none');

    if (def.page && def.page > 1) params.set('page', String(def.page));
    return params;
}

/** Reflect the current search into the address bar (replace, not push). */
function persistSearchToUrl(definition = null) {
    try {
        const qs = serializeDefinitionToParams(definition || currentSearchDefinition()).toString();
        window.history.replaceState(null, '', window.location.pathname + (qs ? '?' + qs : ''));
    } catch (e) {
        console.warn('Could not update the address bar', e);
    }
}

/** Multi-select helper: select exactly the given option values (those
 *  that exist); null/undefined leaves the control untouched. */
function setMultiSelectValues(selectId, values) {
    if (values === null || values === undefined) return;
    const select = document.getElementById(selectId);
    if (!select) return;
    const wanted = new Set((values || []).map(v => String(v)));
    Array.from(select.options).forEach(opt => {
        opt.selected = wanted.has(opt.value);
    });
}

/** Apply a search definition (from the URL or a saved search) to the
 *  on-screen controls. Absent optional fields keep their defaults. */
function applyDefinitionToControls(def) {
    const filters = def.filters || {};
    const options = def.options || {};

    const mainInput = document.getElementById('mainSearchInput');
    if (mainInput) {
        mainInput.value = def.query || '';
        const clearBtn = document.getElementById('clearSearchBtn');
        if (clearBtn) clearBtn.style.display = def.query ? 'block' : 'none';
    }
    searchState.query = def.query || '';

    if (['uncategorized', 'all', 'categorized'].includes(def.scope)) {
        searchState.scope = def.scope;
        const radio = document.querySelector(`input[name="analystScope"][value="${def.scope}"]`);
        if (radio) radio.checked = true;
    }

    const sortSelect = document.getElementById('sortBy');
    if (sortSelect && def.sort_by) sortSelect.value = def.sort_by;

    const caseEl = document.getElementById('caseSensitive');
    if (caseEl) caseEl.checked = !!options.case_sensitive;
    const wholeEl = document.getElementById('wholeWord');
    if (wholeEl) wholeEl.checked = !!options.whole_word;
    const fuzzyEl = document.getElementById('useFuzzy');
    if (fuzzyEl) fuzzyEl.checked = options.use_fuzzy !== false;
    searchState.options = {
        caseSensitive: !!options.case_sensitive,
        wholeWord: !!options.whole_word,
        useFuzzy: options.use_fuzzy !== false
    };

    setMultiSelectValues('fileType', filters.file_type);
    setMultiSelectValues('categoriesSelect', filters.category_id);
    setMultiSelectValues('analystCategoriesFilter', filters.analyst_category_id);
    setMultiSelectValues('sourcesSelect', filters.source_id);
    setMultiSelectValues('sidesSelect', filters.side_id);

    const from = document.getElementById('dateFrom');
    if (from) from.value = filters.date_from || '';
    const to = document.getElementById('dateTo');
    if (to) to.value = filters.date_to || '';

    if (Array.isArray(filters.status)) {
        const readEl = document.getElementById('statusRead');
        const unreadEl = document.getElementById('statusUnread');
        if (readEl) readEl.checked = filters.status.includes('Read');
        if (unreadEl) unreadEl.checked = filters.status.includes('Unread');
    }
}

/** Parse a search definition from the current URL. Returns null when no
 *  search parameters are present. */
function readDefinitionFromUrl() {
    const params = new URLSearchParams(window.location.search);
    if (!SEARCH_URL_PARAMS.some(k => params.has(k))) return null;

    const statusParam = params.get('st');
    let status;
    if (statusParam === 'none') {
        status = [];
    } else if (statusParam) {
        const parts = statusParam.split(',').map(s => s.trim().toLowerCase());
        status = [];
        if (parts.includes('read')) status.push('Read');
        if (parts.includes('unread')) status.push('Unread');
    }

    return {
        query: params.get('q') || '',
        scope: params.get('scope') || undefined,
        sort_by: params.get('sort') || undefined,
        page: Math.max(1, parseInt(params.get('page'), 10) || 1),
        options: {
            case_sensitive: params.get('cs') === '1',
            whole_word: params.get('ww') === '1',
            use_fuzzy: params.get('fz') !== '0'
        },
        filters: {
            file_type: params.getAll('ft'),
            category_id: params.getAll('cat').map(v => parseInt(v, 10)).filter(v => !isNaN(v)),
            analyst_category_id: params.getAll('acat').map(v => parseInt(v, 10)).filter(v => !isNaN(v)),
            source_id: params.getAll('src').map(v => parseInt(v, 10)).filter(v => !isNaN(v)),
            side_id: params.getAll('side').map(v => parseInt(v, 10)).filter(v => !isNaN(v)),
            date_from: params.get('df') || null,
            date_to: params.get('dt') || null,
            status: status
        }
    };
}

/** Restore a search from the URL into the controls. True when restored. */
function restoreSearchFromUrl() {
    const def = readDefinitionFromUrl();
    if (!def) return false;
    applyDefinitionToControls(def);
    searchState.currentPage = def.page;
    updateFilterChips();
    return true;
}

function restoreSearchFromUrlAndRun() {
    if (restoreSearchFromUrl()) {
        executeAdvancedSearch();
    }
}

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

    const suggestionsList = document.getElementById('suggestionsList');
    suggestionsList?.addEventListener('click', (event) => {
        const item = event.target.closest('[data-suggestion]');
        if (item && suggestionsList.contains(item)) selectSuggestion(item.dataset.suggestion || '');
    });

    const filterChips = document.getElementById('filtersChips');
    filterChips?.addEventListener('click', (event) => {
        const button = event.target.closest('[data-remove-filter-chip]');
        if (button && filterChips.contains(button)) {
            removeFilterChip(button.dataset.filterType || '', button.dataset.filterId || '');
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
        <button type="button" class="suggestion-item" data-suggestion="${escapeAttr(suggestion)}">
            <i class="bi bi-search" aria-hidden="true"></i>
            <span>${highlightMatch(suggestion, query)}</span>
        </button>
    `).join('');
    
    dropdown.classList.add('active');
    document.getElementById('mainSearchInput')?.setAttribute('aria-expanded', 'true');
}

// Render suggestion text safely while marking query matches.
function highlightMatch(text, query) {
    return highlightQueryTerms(text, query);
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
    document.getElementById('mainSearchInput')?.setAttribute('aria-expanded', 'false');
}

// Update filter chips
function updateFilterChips() {
    const chips = [];
    
    // File types
    const fileTypes = Array.from(document.getElementById('fileType').selectedOptions).map(o => o.value);
    if (fileTypes.length > 0) {
        fileTypes.forEach(type => {
            if (type) chips.push({ type: 'fileType', label: tPage('fileType', 'File Type'), value: type, id: type });
        });
    }
    
    // Categories (smart taxonomy - separate from analyst categories, FR-1.4)
    const categoriesSelect = document.getElementById('categoriesSelect');
    const categories = Array.from(categoriesSelect.selectedOptions).map(o => o.value);
    if (categories.length > 0) {
        categories.forEach(catId => {
            const option = Array.from(categoriesSelect.options).find(candidate => candidate.value === catId);
            if (option) {
                chips.push({ type: 'category', label: tPage('smartCategory', 'Smart Category'), value: option.textContent, id: catId });
            }
        });
    }

    // Analyst categories (manual taxonomy - separate namespace, FR-1.4)
    const analystFilter = document.getElementById('analystCategoriesFilter');
    if (analystFilter) {
        Array.from(analystFilter.selectedOptions).forEach(opt => {
            chips.push({ type: 'analystCategory', label: tPage('analystCategory', 'Analyst Category'), value: opt.textContent, id: opt.value });
        });
    }
    
    // Sources
    const sourcesSelect = document.getElementById('sourcesSelect');
    const sources = Array.from(sourcesSelect.selectedOptions).map(o => o.value);
    if (sources.length > 0) {
        sources.forEach(sourceId => {
            const option = Array.from(sourcesSelect.options).find(candidate => candidate.value === sourceId);
            if (option) {
                chips.push({ type: 'source', label: tPage('source', 'Source'), value: option.textContent, id: sourceId });
            }
        });
    }
    
    // Sides
    const sidesSelect = document.getElementById('sidesSelect');
    const sides = Array.from(sidesSelect.selectedOptions).map(o => o.value);
    if (sides.length > 0) {
        sides.forEach(sideId => {
            const option = Array.from(sidesSelect.options).find(candidate => candidate.value === sideId);
            if (option) {
                chips.push({ type: 'side', label: tPage('side', 'Side'), value: option.textContent, id: sideId });
            }
        });
    }
    
    // Date range
    const dateFrom = document.getElementById('dateFrom').value;
    const dateTo = document.getElementById('dateTo').value;
    if (dateFrom) {
        chips.push({ type: 'dateFrom', label: tPage('from', 'From'), value: dateFrom });
    }
    if (dateTo) {
        chips.push({ type: 'dateTo', label: tPage('to', 'To'), value: dateTo });
    }
    
    // Status
    const statusRead = document.getElementById('statusRead').checked;
    const statusUnread = document.getElementById('statusUnread').checked;
    if (statusRead && !statusUnread) {
        // Read is the default status, so it is not shown as an active filter.
    } else if (!statusRead && statusUnread) {
        chips.push({ type: 'status', label: tPage('status', 'Status'), value: tPage('pending', 'Pending') });
    } else if (!statusRead && !statusUnread) {
        chips.push({ type: 'status', label: tPage('status', 'Status'), value: tPage('noStatusesSelected', 'No statuses selected') });
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
    chipsEl.innerHTML = chips.map((chip) => {
        const chipClass = chip.priority ? 'filter-chip priority-chip' : 'filter-chip';
        const type = escapeAttr(chip.type || '');
        const id = escapeAttr(chip.id == null ? '' : chip.id);
        return `
            <div class="${chipClass}">
                <span class="chip-label">${escapeHtml(chip.label)}:</span>
                <span class="chip-value">${escapeHtml(chip.value)}</span>
                <button type="button" class="chip-remove" data-remove-filter-chip="true"
                        data-filter-type="${type}" data-filter-id="${id}"
                        aria-label="${escapeAttr(tPage('removeFilter', 'Remove filter'))}">
                    <i class="bi bi-x" aria-hidden="true"></i>
                </button>
            </div>
        `;
    }).join('');
}

// Remove filter chip
function removeFilterChip(type, id) {
    {
        // Handle regular filters
        switch (type) {
            case 'fileType':
                const fileTypeSelect = document.getElementById('fileType');
                const fileTypeOption = Array.from(fileTypeSelect.options).find(option => option.value === String(id));
                if (fileTypeOption) fileTypeOption.selected = false;
                break;
            case 'category':
                const categorySelect = document.getElementById('categoriesSelect');
                const categoryOption = Array.from(categorySelect.options).find(option => option.value === String(id));
                if (categoryOption) categoryOption.selected = false;
                break;
            case 'analystCategory':
                const analystFilter = document.getElementById('analystCategoriesFilter');
                if (analystFilter) {
                    const analystOption = Array.from(analystFilter.options).find(option => option.value === String(id));
                    if (analystOption) analystOption.selected = false;
                }
                break;
            case 'source':
                const sourceSelect = document.getElementById('sourcesSelect');
                const sourceOption = Array.from(sourceSelect.options).find(option => option.value === String(id));
                if (sourceOption) sourceOption.selected = false;
                break;
            case 'side':
                const sideSelect = document.getElementById('sidesSelect');
                const sideOption = Array.from(sideSelect.options).find(option => option.value === String(id));
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

// Map the user-facing sort choices to the API's stable field/direction pair.
function getAdvancedSortDefinition(choice = document.getElementById('sortBy')?.value || 'relevance') {
    const sortMap = {
        relevance: { sort_by: 'relevance', sort_order: 'desc' },
        date: { sort_by: 'date', sort_order: 'desc' },
        date_old: { sort_by: 'date', sort_order: 'asc' },
        name: { sort_by: 'name', sort_order: 'asc' },
        size: { sort_by: 'size', sort_order: 'desc' },
    };
    return sortMap[choice] || sortMap.relevance;
}

// Execute advanced search
async function executeAdvancedSearch() {
    const startTime = performance.now();
    const query = document.getElementById('mainSearchInput')?.value.trim() || '';
    const filters = collectFilters();

    if (!query && getActiveFiltersCount() === 0) {
        alert('Please enter a search query or select filters');
        return;
    }

    // Confirm before changing selection or entering a loading state. Returning
    // here must leave the previous results usable, not strand a spinner.
    if (!filters.source_id.length && !filters.side_id.length && !query) {
        const confirmSearch = confirm(tPage('largeSearchConfirm',
            'Searching without a source or side filter may be slow on large datasets. Continue?'));
        if (!confirmSearch) return;
    }

    hideSuggestions();
    searchState.query = query;

    // A new search invalidates the previous result selection (FR-1.2).
    searchState.selectedIds = new Set();
    updateSelectionBar();

    // Cancel any previous request so a slower response cannot overwrite the
    // newer query/filter selection.
    activeAdvancedSearchController?.abort();
    const controller = new AbortController();
    activeAdvancedSearchController = controller;
    const requestSequence = ++advancedSearchRequestSequence;
    showLoading();

    const options = {
        case_sensitive: document.getElementById('caseSensitive')?.checked || false,
        whole_word: document.getElementById('wholeWord')?.checked || false,
        use_fuzzy: document.getElementById('useFuzzy')?.checked !== false
    };
    searchState.options = {
        caseSensitive: options.case_sensitive,
        wholeWord: options.whole_word,
        useFuzzy: options.use_fuzzy
    };
    const sort = getAdvancedSortDefinition();
    const definition = {
        query,
        scope: searchState.scope,
        sort_by: document.getElementById('sortBy')?.value || 'relevance',
        page: searchState.currentPage,
        options,
        filters
    };

    try {
        const params = new URLSearchParams({
            query,
            page: String(searchState.currentPage),
            per_page: String(searchState.resultsPerPage),
            use_advanced: 'true',
            use_fulltext: 'true',
            use_bm25: 'true',
            use_expansion: 'true',
            use_fuzzy: options.use_fuzzy ? 'true' : 'false',
            sort_by: sort.sort_by,
            sort_order: sort.sort_order
        });

        // Analyst-categorization search scope (FR-2.x). Always sent so the
        // server can persist the selection in the session (FR-2.3).
        params.set('scope', searchState.scope);

        if (filters.file_type.length > 0) {
            filters.file_type.forEach(type => params.append('file_type', type));
        }
        if (filters.category_id.length > 0) {
            filters.category_id.forEach(id => params.append('category_id', String(id)));
        }
        if (filters.analyst_category_id.length > 0) {
            filters.analyst_category_id.forEach(id => params.append('analyst_category_id', String(id)));
        }
        if (filters.source_id.length > 0) {
            filters.source_id.forEach(id => params.append('source_id', String(id)));
        }
        if (filters.side_id.length > 0) {
            filters.side_id.forEach(id => params.append('side_id', String(id)));
        }
        if (filters.date_from) params.append('date_from', filters.date_from);
        if (filters.date_to) params.append('date_to', filters.date_to);

        // The status checkboxes represent paths.file_status (Read/Unread).
        // Send an explicit sentinel when both are cleared so the API returns
        // no statuses rather than silently dropping the filter.
        if (filters.status.length > 0) {
            filters.status.forEach(status => params.append('status', status));
        } else {
            params.append('status', 'none');
        }

        const response = await fetch(`/api/search?${params.toString()}`, {
            signal: controller.signal
        });
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        const data = await response.json();
        if (controller.signal.aborted || requestSequence !== advancedSearchRequestSequence) return;

        searchState.searchTime = ((performance.now() - startTime) / 1000).toFixed(2);
        if (Array.isArray(data.results)) {
            searchState.results = data.results;
            searchState.totalResults = Number(data.pagination?.total) || data.results.length;
            displayResults(data.results, data.pagination);
        } else {
            searchState.results = [];
            searchState.totalResults = 0;
            displayResults([], null);
        }

        // Keep the address bar and exports tied to the exact definition that
        // produced these rows, not controls the reader may have since edited.
        searchState.lastDefinition = definition;
        persistSearchToUrl(definition);
    } catch (error) {
        if (error.name === 'AbortError' || requestSequence !== advancedSearchRequestSequence) return;
        console.error('Search error:', error);
        alert(tPage('searchError', 'Search error') + ': ' + error.message);
        searchState.results = [];
        searchState.totalResults = 0;
        displayResults([], null);
    } finally {
        if (requestSequence === advancedSearchRequestSequence) {
            activeAdvancedSearchController = null;
            hideLoading();
        }
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
        if (!result || typeof result !== 'object') return '';
        const fileId = Number(result.id);
        if (!Number.isSafeInteger(fileId) || fileId < 1) return '';
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
            <div class="result-item ${searchState.selectedIds.has(fileId) ? 'result-selected' : ''}" data-file-id="${fileId}">
                <div class="result-select" onclick="event.stopPropagation()">
                    <input class="form-check-input result-checkbox" type="checkbox"
                           ${searchState.selectedIds.has(fileId) ? 'checked' : ''}
                           onchange="toggleResultSelection(${fileId}, this.checked)"
                           title="${escapeAttr(tPage('selectForCategorization', 'Select for manual categorization'))}"
                           aria-label="${escapeAttr(tPage('selectFileForCategorization', 'Select {file} for manual categorization').replace('{file}', result.file_name || 'file'))}">
                </div>
                <div class="result-body" onclick="openResultInNewTab(event, ${fileId})"
                     title="${escapeAttr(tPage('openInNewTab', 'Open in new tab'))}">
                    <div class="result-title-row">
                        <span class="result-file-icon ${typeInfo.css}" title="${escapeAttr(fileType || '')}">
                            <i class="bi ${typeInfo.icon}" aria-hidden="true"></i>
                        </span>
                        <a class="result-title result-title-link" href="${fileDetailHref(fileId)}"
                           target="_blank" rel="noopener"
                           onclick="event.stopPropagation()">${escapeHtml(result.file_name || tPage('untitled', 'Untitled'))}</a>
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
                    <div class="result-hover-actions">
                        <button type="button" class="result-action-btn result-action-preview"
                                onclick="showFilePreview(${fileId}); event.stopPropagation();"
                                title="${escapeAttr(tPage('preview', 'Quick preview (stays on this page)'))}"
                                aria-label="${escapeAttr(tPage('preview', 'Quick preview (stays on this page)'))}">
                            <i class="bi bi-eye" aria-hidden="true"></i>
                        </button>
                        <button type="button" class="result-action-btn result-action-open"
                                onclick="openResultInNewTab(event, ${fileId})"
                                title="${escapeAttr(tPage('openInNewTab', 'Open in new tab'))}"
                                aria-label="${escapeAttr(tPage('openInNewTab', 'Open in new tab'))}">
                            <i class="bi bi-box-arrow-up-right" aria-hidden="true"></i>
                        </button>
                    </div>
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

// Escape and highlight query terms without ever treating source text as HTML.
function highlightQueryTerms(text, query) {
    const source = String(text == null ? '' : text);
    const terms = parseQueryTerms(String(query || '')).filter(Boolean);
    if (!terms.length) return escapeHtml(source);

    const alternatives = [...new Set(terms)]
        .sort((a, b) => b.length - a.length)
        .map(term => term.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'));
    const matcher = new RegExp(`(${alternatives.join('|')})`, 'gi');
    let output = '';
    let lastIndex = 0;
    for (const match of source.matchAll(matcher)) {
        output += escapeHtml(source.slice(lastIndex, match.index));
        output += `<mark>${escapeHtml(match[0])}</mark>`;
        lastIndex = match.index + match[0].length;
    }
    return output + escapeHtml(source.slice(lastIndex));
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
    // Read-only is the default; both checked means all statuses (no filter).
    // An explicit unread-only or empty selection remains an active filter.
    if (!document.getElementById('statusRead').checked) count++;
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

// Feeling lucky (get first result) — opens in a NEW tab so the search
// page (and its results) stay intact.
async function feelingLucky() {
    searchState.resultsPerPage = 1;
    await executeAdvancedSearch();
    if (searchState.results.length > 0) {
        window.open(fileDetailHref(searchState.results[0].id), '_blank', 'noopener');
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
/**
 * The filters as they stand on screen.
 *
 * Read in one place because two operations depend on them agreeing: the search
 * the reader is looking at, and the export of its result set. An export built
 * from a second reading of the same controls is an export of a different
 * query.
 */
function collectFilters() {
    const sourceIds = Array.from(document.getElementById('sourcesSelect').selectedOptions)
        .map(o => parseInt(o.value)).filter(id => !isNaN(id));
    const sideIds = Array.from(document.getElementById('sidesSelect').selectedOptions)
        .map(o => parseInt(o.value)).filter(id => !isNaN(id));
    const filters = {
        file_type: Array.from(document.getElementById('fileType').selectedOptions)
            .map(o => o.value).filter(v => v),
        category_id: Array.from(document.getElementById('categoriesSelect').selectedOptions)
            .map(o => parseInt(o.value)).filter(id => !isNaN(id)),
        analyst_category_id: Array.from(document.getElementById('analystCategoriesFilter')?.selectedOptions || [])
            .map(o => parseInt(o.value)).filter(v => !isNaN(v)),
        source_id: sourceIds,
        side_id: sideIds,
        date_from: document.getElementById('dateFrom').value || null,
        date_to: document.getElementById('dateTo').value || null,
        status: [],
    };
    if (document.getElementById('statusRead').checked) filters.status.push('Read');
    if (document.getElementById('statusUnread').checked) filters.status.push('Unread');
    return filters;
}

async function exportResults(format = 'csv') {
    if (searchState.results.length === 0) {
        Toast.info(tPage('nothingToExport', 'No results to export.'));
        return;
    }

    // The definition that produced the visible rows, not the current controls
    // and never the browser's result array. The server re-runs this query.
    const definition = searchState.lastDefinition;
    if (!definition) {
        Toast.info(tPage('nothingToExport', 'No results to export.'));
        return;
    }
    const filters = definition.filters || {};
    const options = definition.options || {};
    const sort = getAdvancedSortDefinition(definition.sort_by);
    const payload = {
        query: definition.query || '',
        export_scope: 'filtered',
        analyst_scope: definition.scope || 'uncategorized',
        format,
        sort_by: sort.sort_by,
        sort_order: sort.sort_order,
        source_ids: filters.source_id || [],
        side_ids: filters.side_id || [],
        category_ids: filters.category_id || [],
        analyst_category_ids: filters.analyst_category_id || [],
        file_type: filters.file_type || [],
        status: filters.status || [],
        date_from: filters.date_from || null,
        date_to: filters.date_to || null,
        use_advanced: true,
        use_fulltext: true,
        use_bm25: true,
        use_expansion: true,
        use_fuzzy: options.use_fuzzy !== false,
    };

    try {
        const response = await fetch('/api/search/export', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': document.querySelector('meta[name="csrf-token"]')?.getAttribute('content') || '',
            },
            body: JSON.stringify(payload),
        });

        if (!response.ok) {
            const problem = await response.json().catch(() => ({}));
            Toast.error(problem.error || tPage('exportFailed', 'The export could not be produced.'));
            return;
        }

        const blob = await response.blob();
        const rows = response.headers.get('X-Export-Rows') || '';
        const truncated = response.headers.get('X-Export-Truncated') === 'true';
        const disposition = response.headers.get('Content-Disposition') || '';
        const named = disposition.match(/filename\*?=(?:UTF-8''|")?([^";]+)/i);
        downloadBlob(blob, named
            ? decodeURIComponent(named[1].replace(/"/g, ''))
            : `search_export_${new Date().toISOString().split('T')[0]}.${format}`);

        // Say what was exported, and say it out loud when it was capped.
        if (truncated) {
            Toast.warning(tPage('exportTruncated',
                'The export reached the size limit; narrow the query to get everything.'),
                {detail: `${rows} rows`});
        } else {
            Toast.success(tPage('exportReady', 'Export ready.'), {detail: `${rows} rows`});
        }
    } catch (error) {
        Toast.error(tPage('exportFailed', 'The export could not be produced.'));
    }
}

// Print results
function printResults() {
    if (searchState.results.length === 0) {
        alert('No results to print');
        return;
    }
    
    const query = searchState.lastDefinition?.query || 'Search Results';
    const printWindow = window.open('', '_blank');
    if (!printWindow) {
        Toast.error(tPage('printWindowBlocked', 'Allow pop-ups to print these results.'));
        return;
    }
    const safeQuery = escapeHtml(query);

    const printContent = `
<!DOCTYPE html>
<html>
<head>
    <title>Search Results - ${safeQuery}</title>
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
    <h1>Search Results: ${safeQuery}</h1>
    <div class="header-info">
        <p><strong>Results on this page:</strong> ${searchState.results.length.toLocaleString()}</p>
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

// ====================================================================
// In-page file preview (popup) — inspect a result without leaving the
// search page; the full file page stays one click away in a new tab.
// The search page itself is never navigated away from.
// ====================================================================

const previewModal = { el: null, bodyEl: null, titleEl: null, openBtn: null, currentFileId: null };

function ensurePreviewModal() {
    if (previewModal.el) return previewModal;
    const overlay = document.createElement('div');
    overlay.id = 'searchFilePreviewModal';
    overlay.className = 'sfp-overlay';
    overlay.innerHTML = `
        <div class="sfp-dialog" role="dialog" aria-modal="true"
             aria-label="${escapeAttr(tPage('preview', 'File preview'))}">
            <div class="sfp-header">
                <span class="sfp-title" id="sfpTitle"></span>
                <div class="sfp-header-actions">
                    <a class="sfp-open-full" id="sfpOpenFull" href="#" target="_blank" rel="noopener">
                        <i class="bi bi-box-arrow-up-right me-1" aria-hidden="true"></i>
                        <span>${escapeHtml(tPage('openInNewTab', 'Open in new tab'))}</span>
                    </a>
                    <button type="button" class="sfp-close" id="sfpClose"
                            title="${escapeAttr(tPage('closePreview', 'Close preview'))}"
                            aria-label="${escapeAttr(tPage('closePreview', 'Close preview'))}">
                        <i class="bi bi-x-lg" aria-hidden="true"></i>
                    </button>
                </div>
            </div>
            <div class="sfp-body" id="sfpBody"></div>
        </div>`;
    document.body.appendChild(overlay);
    previewModal.el = overlay;
    previewModal.bodyEl = overlay.querySelector('#sfpBody');
    previewModal.titleEl = overlay.querySelector('#sfpTitle');
    previewModal.openBtn = overlay.querySelector('#sfpOpenFull');
    // Backdrop click closes (mousedown so text-selection drags don't)
    overlay.addEventListener('mousedown', (e) => {
        if (e.target === overlay) hideFilePreview();
    });
    overlay.querySelector('#sfpClose').addEventListener('click', hideFilePreview);
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && previewModal.el.style.display !== 'none') {
            hideFilePreview();
        }
    });
    return previewModal;
}

/** Open the popup preview for a search result (no navigation). */
function showFilePreview(fileId) {
    const modal = ensurePreviewModal();
    previewModal.currentFileId = fileId;
    // The full page opens in a new tab and carries the originating search.
    modal.openBtn.href = fileDetailHref(fileId);
    modal.titleEl.textContent = tPage('previewLoading', 'Loading preview…');
    modal.bodyEl.innerHTML = `
        <div class="sfp-loading">
            <div class="loading-spinner" role="status" aria-live="polite"></div>
            <p>${escapeHtml(tPage('previewLoading', 'Loading preview…'))}</p>
        </div>`;
    modal.el.style.display = 'flex';
    document.body.classList.add('sfp-no-scroll');

    fetch(`/api/preview/${fileId}`)
        .then(response => {
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            return response.json();
        })
        .then(data => {
            if (previewModal.currentFileId !== fileId) return; // a newer request won
            renderPreviewPayload(data, fileId);
        })
        .catch(error => {
            if (previewModal.currentFileId !== fileId) return;
            console.error('Preview failed:', error);
            previewModal.bodyEl.innerHTML = `
                <div class="sfp-message">
                    <i class="bi bi-exclamation-triangle" aria-hidden="true"></i>
                    <p>${escapeHtml(tPage('previewFailed', 'Preview failed'))}: ${escapeHtml(error.message)}</p>
                    <p class="sfp-message-hint">${escapeHtml(tPage('openFullPageHint', 'Open the file in a new tab to view the full content.'))}</p>
                </div>`;
        });
}

function hideFilePreview() {
    if (!previewModal.el) return;
    previewModal.el.style.display = 'none';
    previewModal.currentFileId = null;
    previewModal.bodyEl.innerHTML = '';
    document.body.classList.remove('sfp-no-scroll');
}

function renderPreviewPayload(data, fileId) {
    const body = previewModal.bodyEl;
    const name = data.file_name || tPage('untitled', 'Untitled');
    previewModal.titleEl.textContent = name;
    const type = data.preview_type;

    if (type === 'image' && data.data) {
        // data is a full data: URI produced by the preview service
        body.innerHTML = `
            <div class="sfp-image-wrap">
                <img class="sfp-image" src="${escapeAttr(data.data)}" alt="${escapeAttr(name)}">
            </div>`;
    } else if ((type === 'text' || type === 'document' || type === 'pdf') && data.data) {
        const note = type === 'pdf' && data.page_count
            ? `<div class="sfp-note">${escapeHtml(tPage('pdfFirstPage', 'First page text'))} · ${data.page_count} ${escapeHtml(tPage('pages', 'pages'))}</div>`
            : '';
        // The highlighter escapes source text and emits only its own <mark> tags.
        body.innerHTML = `${note}<pre class="sfp-text">${highlightQueryTerms(String(data.data), searchState.query)}</pre>`;
    } else if (type === 'unsupported') {
        body.innerHTML = `
            <div class="sfp-message">
                <i class="bi bi-file-earmark-lock" aria-hidden="true"></i>
                <p>${escapeHtml(data.message || tPage('previewUnavailable', 'Preview is not available for this file.'))}</p>
                <p class="sfp-message-hint">${escapeHtml(tPage('openFullPageHint', 'Open the file in a new tab to view the full content.'))}</p>
            </div>`;
    } else {
        const detail = data.error || tPage('previewUnavailable', 'Preview is not available for this file.');
        body.innerHTML = `
            <div class="sfp-message">
                <i class="bi bi-exclamation-circle" aria-hidden="true"></i>
                <p>${escapeHtml(detail)}</p>
                <p class="sfp-message-hint">${escapeHtml(tPage('openFullPageHint', 'Open the file in a new tab to view the full content.'))}</p>
            </div>`;
    }
}

// ====================================================================
// Saved searches — store the full search definition (query, filters,
// scope, options, sort) server-side and re-run it any time without
// searching again.
// ====================================================================

let savedSearchesCache = null;

/** Save the current search (query + all filters + scope + options). */
async function saveCurrentSearch() {
    const def = currentSearchDefinition();
    if (!def.query && getActiveFiltersCount() === 0) {
        Toast.info(tPage('nothingToSave', 'Run a search first, then save it here.'));
        return;
    }

    const stamp = new Date().toISOString().split('T')[0];
    const suggested = def.query || `${tPage('savedSearch', 'Saved search')} ${stamp}`;
    const name = prompt(tPage('saveSearchPrompt', 'Name this search:'), suggested);
    if (name === null) return; // cancelled
    const trimmed = (name.trim() || suggested);

    try {
        const response = await fetch('/api/search/saved', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': analystCsrftoken()
            },
            body: JSON.stringify({
                name: trimmed,
                query: def.query,
                filters: {
                    ...def.filters,
                    scope: def.scope,
                    sort_by: def.sort_by,
                    options: def.options
                }
            })
        });
        const data = await response.json();
        if (!response.ok || !data.success) {
            throw new Error(data.error || `HTTP ${response.status}`);
        }
        savedSearchesCache = null; // re-fetch next time the menu opens
        Toast.success(tPage('searchSaved', 'Search saved. Find it under Saved searches.'));
    } catch (error) {
        console.error('Saving the search failed:', error);
        Toast.error(tPage('saveFailed', 'Could not save this search.') + ' ' + error.message);
    }
}

/** Open/close the saved-searches dropdown (fetches lazily). */
async function toggleSavedSearchMenu() {
    const menu = document.getElementById('savedSearchMenu');
    if (!menu) return;
    if (menu.style.display === 'block') {
        menu.style.display = 'none';
        return;
    }
    menu.style.display = 'block';
    await renderSavedSearchMenu();
}

// Close the dropdown when clicking anywhere outside it
document.addEventListener('click', (e) => {
    const menu = document.getElementById('savedSearchMenu');
    if (menu && menu.style.display === 'block' &&
        !menu.contains(e.target) && !e.target.closest('.saved-search-container')) {
        menu.style.display = 'none';
    }
});

async function renderSavedSearchMenu() {
    const list = document.getElementById('savedSearchMenuList');
    if (!list) return;
    list.innerHTML = `<div class="ssm-status">${escapeHtml(tPage('loadingSaved', 'Loading saved searches…'))}</div>`;
    try {
        if (!savedSearchesCache) {
            const response = await fetch('/api/search/saved');
            const data = await response.json();
            savedSearchesCache = data.searches || [];
        }
        const searches = savedSearchesCache;
        if (searches.length === 0) {
            list.innerHTML = `<div class="ssm-status">${escapeHtml(tPage('noSavedSearches', 'No saved searches yet. Run a search and press Save.'))}</div>`;
            return;
        }
        list.innerHTML = searches.map(s => `
            <div class="ssm-item">
                <button type="button" class="ssm-run" onclick="applySavedSearchById(${s.id})"
                        title="${escapeAttr(tPage('runSavedSearch', 'Run this search'))}">
                    <span class="ssm-name">${escapeHtml(s.name)}</span>
                    ${s.query ? `<span class="ssm-query">${escapeHtml(s.query)}</span>` : ''}
                </button>
                <button type="button" class="ssm-delete" onclick="deleteSavedSearchById(${s.id}, event)"
                        title="${escapeAttr(tPage('deleteSearch', 'Delete'))}"
                        aria-label="${escapeAttr(tPage('deleteSearch', 'Delete'))}">
                    <i class="bi bi-trash" aria-hidden="true"></i>
                </button>
            </div>`).join('');
    } catch (error) {
        console.error('Loading saved searches failed:', error);
        list.innerHTML = `<div class="ssm-status">${escapeHtml(tPage('loadSavedFailed', 'Could not load saved searches.'))}</div>`;
    }
}

/** Re-run a saved search: restore every control, then search. */
async function applySavedSearchById(id) {
    try {
        // Fetching the single search also marks it used (server-side).
        const response = await fetch(`/api/search/saved/${id}`);
        const data = await response.json();
        if (!response.ok || !data.search) {
            throw new Error(data.error || `HTTP ${response.status}`);
        }
        applySavedSearch(data.search);
    } catch (error) {
        console.error('Applying the saved search failed:', error);
        Toast.error(tPage('applyFailed', 'Could not run this saved search.'));
    }
}

function applySavedSearch(search) {
    const f = search.filters || {};
    const def = {
        query: search.query || '',
        scope: f.scope || 'uncategorized',
        sort_by: f.sort_by || 'relevance',
        page: 1,
        options: f.options || { case_sensitive: false, whole_word: false, use_fuzzy: true },
        filters: {
            file_type: f.file_type || [],
            category_id: f.category_id || [],
            analyst_category_id: f.analyst_category_id || [],
            source_id: f.source_id || [],
            side_id: f.side_id || [],
            date_from: f.date_from || null,
            date_to: f.date_to || null,
            status: Array.isArray(f.status) ? f.status : undefined
        }
    };
    applyDefinitionToControls(def);
    searchState.currentPage = 1;
    // A different search invalidates the previous result selection (FR-1.2)
    searchState.selectedIds = new Set();
    updateSelectionBar();
    updateFilterChips();

    const menu = document.getElementById('savedSearchMenu');
    if (menu) menu.style.display = 'none';

    executeAdvancedSearch();
    Toast.success(
        tPage('searchApplied', 'Saved search applied')
            .replace('{name}', search.name || '')
    );
}

/** Delete a saved search from the dropdown. */
async function deleteSavedSearchById(id, evt) {
    if (evt) {
        evt.preventDefault();
        evt.stopPropagation();
    }
    if (!confirm(tPage('deleteSearchConfirm', 'Are you sure you want to delete this saved search?'))) {
        return;
    }
    try {
        const response = await fetch(`/api/search/saved/${id}`, {
            method: 'DELETE',
            headers: { 'X-CSRFToken': analystCsrftoken() }
        });
        const data = await response.json();
        if (!response.ok || !data.success) {
            throw new Error(data.error || `HTTP ${response.status}`);
        }
        savedSearchesCache = null;
        await renderSavedSearchMenu();
        Toast.success(tPage('searchDeleted', 'Saved search deleted'));
    } catch (error) {
        console.error('Deleting the saved search failed:', error);
        Toast.error(tPage('deleteFailed', 'Could not delete this saved search.'));
    }
}

// Open a search result in a NEW tab: the search page keeps its results,
// query and filters untouched (the core "search is lost" fix).
function openResultInNewTab(event, fileId) {
    if (event) {
        event.preventDefault();
        event.stopPropagation();
    }
    window.open(fileDetailHref(fileId), '_blank', 'noopener');
}

// Expose functions globally
if (typeof window !== 'undefined') {
    window.executeAdvancedSearch = executeAdvancedSearch;
    window.resetAllFilters = resetAllFilters;
    window.clearAllFilters = clearAllFilters;
    window.toggleFiltersPanel = toggleFiltersPanel;
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
    // Result opening (new tab / popup preview) and saved searches
    window.openResultInNewTab = openResultInNewTab;
    window.showFilePreview = showFilePreview;
    window.hideFilePreview = hideFilePreview;
    window.saveCurrentSearch = saveCurrentSearch;
    window.toggleSavedSearchMenu = toggleSavedSearchMenu;
    window.applySavedSearchById = applySavedSearchById;
    window.deleteSavedSearchById = deleteSavedSearchById;
    console.log('Advanced Search functions exposed globally');
}
