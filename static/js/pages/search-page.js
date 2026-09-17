/**
 * Search Page JavaScript
 * Handles the basic search workspace with DOM-safe result rendering,
 * stable controls, and delegated pagination actions.
 */

import { apiGet } from '../modules/api/api-client.js';
import { endpoints } from '../modules/api/endpoints.js';

let initialized = false;
let translations = {};

function readPageData() {
    const node = document.getElementById('search-page-data');
    if (!node) return {};
    try {
        return JSON.parse(node.textContent || '{}');
    } catch (error) {
        console.warn('Search page data could not be parsed', error);
        return {};
    }
}

function t(key, fallback) {
    return translations[key] || fallback;
}

function notify(message, type = 'warning') {
    if (window.MessageSystem && typeof window.MessageSystem.show === 'function') {
        window.MessageSystem.show(message, type, { duration: 3000 });
        return;
    }
    if (type === 'error' && window.showError) {
        window.showError(message);
        return;
    }
    console[type === 'error' ? 'error' : 'warn'](message);
}

function element(tagName, options = {}) {
    const el = document.createElement(tagName);
    if (options.className) el.className = options.className;
    if (options.text !== undefined) el.textContent = options.text;
    if (options.attrs) {
        Object.entries(options.attrs).forEach(([key, value]) => el.setAttribute(key, value));
    }
    return el;
}

function ensureResultsSection(query = '') {
    let container = document.getElementById('searchResults');
    if (container) return container;

    const workspace = document.querySelector('.search-workspace') || document.querySelector('main') || document.body;
    const section = element('section', {
        className: 'section-card search-results-section ia-scroll-framed-section',
        attrs: { 'aria-labelledby': 'searchResultsTitle' }
    });

    const header = element('div', { className: 'section-header search-results-header ia-control-surface', attrs: { 'data-ia-role': 'controls' } });
    const titleWrap = element('div');
    titleWrap.append(
        element('span', { className: 'search-eyebrow', text: t('results', 'Results') }),
        element('h2', { text: t('searchResults', 'Search Results'), attrs: { id: 'searchResultsTitle' } })
    );
    const meta = element('div', { className: 'search-results-meta' });
    meta.append(element('span', { className: 'search-count-pill', text: `0 ${t('found', 'found')}` }), element('span', { className: 'search-query-pill', text: query ? `“${query}”` : '' }));
    header.append(titleWrap, meta);

    container = element('div', {
        className: 'section-content search-results-container ia-scroll-body',
        attrs: { id: 'searchResults', 'data-ia-role': 'data-region' }
    });

    section.append(header, container);
    workspace.append(section);
    window.InforaxisDataInterface?.refresh?.(section);
    return container;
}

function ensurePaginationContainer() {
    const container = ensureResultsSection();
    let pagination = container.parentElement?.querySelector('.search-results-pagination');
    if (pagination) return pagination;
    pagination = element('div', { className: 'search-results-pagination ia-control-surface d-none', attrs: { 'data-ia-role': 'controls' } });
    container.parentElement?.append(pagination);
    return pagination;
}

function updateResultsHeader(query, totalResults) {
    const section = document.getElementById('searchResults')?.closest('.search-results-section');
    if (!section) return;
    const count = section.querySelector('.search-count-pill');
    const queryPill = section.querySelector('.search-query-pill');
    if (count) count.textContent = `${Number(totalResults || 0).toLocaleString()} ${t('found', 'found')}`;
    if (queryPill) queryPill.textContent = query ? `“${query}”` : '';
}

function clearPagination() {
    const pagination = ensurePaginationContainer();
    pagination.replaceChildren();
    pagination.classList.add('d-none');
}

function renderLoading(query) {
    const container = ensureResultsSection(query);
    updateResultsHeader(query, 0);
    clearPagination();
    const state = element('div', { className: 'empty-state search-empty-state' });
    const spinner = element('div', { className: 'spinner-border', attrs: { role: 'status' } });
    spinner.append(element('span', { className: 'visually-hidden', text: t('loading', 'Loading...') }));
    state.append(spinner);
    container.replaceChildren(state);
}

function renderEmpty(query, message = '') {
    const container = ensureResultsSection(query);
    clearPagination();
    const state = element('div', { className: 'empty-state search-empty-state' });
    state.append(
        element('i', { className: 'bi bi-search', attrs: { 'aria-hidden': 'true' } }),
        element('p', { text: message || `${t('noResults', 'No results found for')} "${query}"` })
    );
    container.replaceChildren(state);
}

function getAdvancedSearchOptions() {
    return {
        use_advanced: document.getElementById('useAdvanced')?.checked !== false,
        use_bm25: document.getElementById('useBM25')?.checked !== false,
        use_expansion: document.getElementById('useExpansion')?.checked !== false,
        use_fuzzy: document.getElementById('useFuzzy')?.checked !== false,
        scope: document.getElementById('scopeSelect')?.value || ''
    };
}

function buildSearchParams(query, page = 1) {
    const advancedOptions = getAdvancedSearchOptions();
    return {
        query,
        page,
        per_page: 10,
        sort_by: 'relevance',
        sort_order: 'desc',
        use_fulltext: 'true',
        use_advanced: advancedOptions.use_advanced ? 'true' : 'false',
        use_bm25: advancedOptions.use_bm25 ? 'true' : 'false',
        use_expansion: advancedOptions.use_expansion ? 'true' : 'false',
        use_fuzzy: advancedOptions.use_fuzzy ? 'true' : 'false',
        scope: advancedOptions.scope
    };
}

async function performEnhancedSearch(query, page = 1) {
    const normalizedQuery = (query || '').trim();
    if (normalizedQuery.length < 2) {
        notify(t('queryTooShort', 'Search query must be at least 2 characters long'), 'warning');
        return;
    }

    renderLoading(normalizedQuery);

    try {
        const data = await apiGet(endpoints.search(buildSearchParams(normalizedQuery, page)));
        displaySearchResults(data, normalizedQuery);

        const url = new URL(window.location);
        url.searchParams.set('q', normalizedQuery);
        url.searchParams.set('page', String(page));
        const scope = document.getElementById('scopeSelect')?.value;
        if (scope) url.searchParams.set('scope', scope);
        window.history.pushState({}, '', url);
    } catch (error) {
        console.error('Search error:', error);
        renderEmpty(normalizedQuery, `${t('errorSearch', 'Error performing search')}: ${error.message || t('unknownError', 'Unknown error')}`);
    }
}

function resultMeta(result) {
    const meta = [];
    if (result.source_name) meta.push(`${t('source', 'Source:')} ${result.source_name}`);
    if (result.side_name) meta.push(`${t('side', 'Side:')} ${result.side_name}`);
    meta.push(`${t('date', 'Date:')} ${result.file_date || t('notAvailable', 'N/A')}`);
    return meta;
}

function createResultCard(result) {
    const fileId = result.id;
    const card = element('a', {
        className: 'ia-record-list-row search-result-card',
        attrs: { href: endpoints.fileDetails ? endpoints.fileDetails(fileId) : `/file/${fileId}` }
    });

    const main = element('div', { className: 'search-result-main' });
    const icon = element('span', { className: 'search-result-icon' });
    icon.append(element('i', { className: 'bi bi-file-earmark', attrs: { 'aria-hidden': 'true' } }));
    const textWrap = element('div');
    const title = element('h3', { text: result.file_name || t('unknownError', 'Unknown') });
    const meta = element('p');
    resultMeta(result).forEach((item) => meta.append(element('span', { text: item })));
    textWrap.append(title, meta);
    main.append(icon, textWrap);

    const side = element('div', { className: 'search-result-side' });
    side.append(element('span', { className: 'search-type-pill', text: result.file_type || '' }));
    if (Array.isArray(result.analyst_categories) && result.analyst_categories.length) {
        const categories = element('div', { className: 'search-category-stack' });
        result.analyst_categories.forEach((category) => categories.append(element('span', { className: 'analyst-category-badge', text: category })));
        side.append(categories);
    }

    card.append(main, side);
    return card;
}

function displaySearchResults(data, query) {
    const container = ensureResultsSection(query);
    const results = data.results || [];
    const pagination = data.pagination || {};
    const totalResults = pagination.total || results.length || 0;
    updateResultsHeader(query, totalResults);

    if (!results.length) {
        renderEmpty(query);
        return;
    }

    const list = element('div', { className: 'ia-record-list search-results-list' });
    results.forEach((result) => list.append(createResultCard(result)));
    container.replaceChildren(list);
    renderPagination(pagination, query);
    highlightSearchTerms();
    window.InforaxisDataInterface?.refresh?.(container.closest('.search-results-section') || container);
}

function visiblePaginationPages(current, total) {
    const pages = [];
    for (let page = 1; page <= total; page += 1) {
        if (page === 1 || page === total || (page >= current - 2 && page <= current + 2)) pages.push(page);
    }
    return pages;
}

function paginationLink(label, page, disabled = false, active = false) {
    const item = element('li', { className: `page-item${disabled ? ' disabled' : ''}${active ? ' active' : ''}` });
    const link = element('a', { className: 'page-link', text: label, attrs: { href: '#', 'data-search-page': String(page) } });
    if (disabled) link.setAttribute('aria-disabled', 'true');
    if (active) link.setAttribute('aria-current', 'page');
    item.append(link);
    return item;
}

function renderPagination(pagination, query) {
    const totalPages = pagination.total_pages || 0;
    const container = ensurePaginationContainer();
    container.replaceChildren();
    if (totalPages <= 1) {
        container.classList.add('d-none');
        return;
    }

    const currentPage = pagination.page || 1;
    const nav = element('nav', { attrs: { 'aria-label': t('paginationLabel', 'Search results pagination') } });
    const list = element('ul', { className: 'pagination justify-content-center mb-0' });
    list.append(paginationLink(t('previous', 'Previous'), currentPage - 1, !pagination.has_prev));
    visiblePaginationPages(currentPage, totalPages).forEach((page) => {
        list.append(paginationLink(String(page), page, false, page === currentPage));
    });
    list.append(paginationLink(t('next', 'Next'), currentPage + 1, !pagination.has_next));
    nav.append(list);
    container.append(nav);
    container.classList.remove('d-none');
    updateResultsHeader(query, pagination.total || 0);
}

async function goToPage(page) {
    const searchInput = document.getElementById('searchQuery');
    const query = searchInput ? searchInput.value.trim() : '';
    if (!query) return;
    await performEnhancedSearch(query, page);
    document.getElementById('searchResults')?.scrollIntoView({ block: 'start', behavior: 'smooth' });
}

function highlightTitle(title, terms) {
    const original = title.dataset.originalText || title.textContent || '';
    title.dataset.originalText = original;
    const fragment = document.createDocumentFragment();
    let remaining = original;
    const lowerTerms = terms.map((term) => term.toLowerCase());

    while (remaining) {
        const lower = remaining.toLowerCase();
        let bestIndex = -1;
        let bestTerm = '';
        lowerTerms.forEach((term) => {
            const index = lower.indexOf(term);
            if (index !== -1 && (bestIndex === -1 || index < bestIndex || (index === bestIndex && term.length > bestTerm.length))) {
                bestIndex = index;
                bestTerm = term;
            }
        });

        if (bestIndex === -1) {
            fragment.append(document.createTextNode(remaining));
            break;
        }

        if (bestIndex > 0) fragment.append(document.createTextNode(remaining.slice(0, bestIndex)));
        const mark = element('mark', { text: remaining.slice(bestIndex, bestIndex + bestTerm.length) });
        fragment.append(mark);
        remaining = remaining.slice(bestIndex + bestTerm.length);
    }

    title.replaceChildren(fragment);
}

function highlightSearchTerms() {
    const searchInput = document.getElementById('searchQuery');
    const query = searchInput ? searchInput.value.trim() : new URLSearchParams(window.location.search).get('q');
    if (!query || query.trim().length < 2) return;

    const terms = query.trim().split(/\s+/).filter((term) => term.length >= 2);
    if (!terms.length) return;
    document.querySelectorAll('.search-result-card h3').forEach((title) => highlightTitle(title, terms));
}

function setupSearchForm() {
    const searchForm = document.getElementById('searchForm');
    const searchInput = document.getElementById('searchQuery');
    if (!searchForm || !searchInput) return;

    searchForm.addEventListener('submit', async (event) => {
        event.preventDefault();
        await performEnhancedSearch(searchInput.value.trim(), 1);
    });

    if (!searchInput.value || searchInput.value.trim() === '') {
        setTimeout(() => searchInput.focus(), 100);
    }
}

function setupSearchPagination() {
    document.addEventListener('click', (event) => {
        if (!(event.target instanceof Element)) return;
        const link = event.target.closest('[data-search-page]');
        if (!link || link.getAttribute('aria-disabled') === 'true') return;
        event.preventDefault();
        goToPage(parseInt(link.getAttribute('data-search-page') || '1', 10));
    });
}

function initSearchPage() {
    if (initialized) return;
    initialized = true;
    const data = readPageData();
    translations = data.translations || {};
    setupSearchForm();
    setupSearchPagination();
    highlightSearchTerms();
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initSearchPage);
} else {
    initSearchPage();
}

export default async function init() {
    initSearchPage();
}

export {
    performEnhancedSearch,
    getAdvancedSearchOptions,
    displaySearchResults,
    goToPage
};
