/**
 * Sources List Page JavaScript
 * Extracted from Sources/sources_list.html
 */

// Load translations from JSON script tag
let translations = {};

document.addEventListener('DOMContentLoaded', function() {
    // Load translations from JSON script tag
    const pageDataEl = document.getElementById('sources-list-page-data');
    if (pageDataEl) {
        try {
            const data = JSON.parse(pageDataEl.textContent);
            translations = data.translations || {};
            // Also make available on window for backward compatibility
            window.translations = window.translations || {};
            Object.assign(window.translations, translations);
        } catch (e) {
            console.error('Error parsing sources list page data:', e);
        }
    }
    
    console.log('Sources list page loaded');
});


// Toast notification helper function
function showToast(message, type = 'info', duration = 4000) {
    const toastContainer = document.getElementById('toastContainer');
    if (!toastContainer) {
        const container = document.createElement('div');
        container.id = 'toastContainer';
        container.className = 'toast-container position-fixed top-0 end-0 p-3';
        container.style.zIndex = '9999';
        document.body.appendChild(container);
    }
    
    const toastId = 'toast-' + Date.now();
    const icons = {
        success: 'check-circle-fill',
        error: 'exclamation-triangle-fill',
        warning: 'exclamation-triangle-fill',
        info: 'info-circle-fill'
    };
    
    const bgColors = {
        success: 'success',
        error: 'danger',
        warning: 'warning',
        info: 'info'
    };
    
    const toastHtml = `
        <div id="${toastId}" class="toast align-items-center text-white bg-${bgColors[type]} border-0" role="alert" aria-live="assertive" aria-atomic="true">
            <div class="d-flex">
                <div class="toast-body">
                    <i class="bi bi-${icons[type]} me-2"></i>
                    ${message}
                </div>
                <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button>
            </div>
        </div>
    `;
    
    document.getElementById('toastContainer').insertAdjacentHTML('beforeend', toastHtml);
    const toastElement = document.getElementById(toastId);
    const toast = new bootstrap.Toast(toastElement, { delay: duration });
    toast.show();
    
    toastElement.addEventListener('hidden.bs.toast', () => {
        toastElement.remove();
    });
}
// Global state for filtering and sorting
let allSources = [];
let filteredSources = [];
let currentPage = 1;
let itemsPerPage = 50;
let currentSort = 'importance-desc';
let currentFormat = 'grid';

// Debounce helper
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}


function escapeHtml(value) {
    const div = document.createElement('div');
    div.textContent = value == null ? '' : String(value);
    return div.innerHTML;
}

function escapeAttr(value) {
    return escapeHtml(value).replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

function safeLocalStorageRef() {
    try {
        return window.localStorage || null;
    } catch (error) {
        return null;
    }
}

function getRecordContainer() {
    return document.getElementById('sourcesCardContainer');
}

function sourceFromElement(item) {
    const dataset = item.dataset || {};
    const displayName = dataset.displayName || item.querySelector('.id-card-name')?.textContent?.trim() || dataset.name || '';
    return {
        id: String(dataset.id || '').trim(),
        name: String(dataset.name || displayName).toLowerCase(),
        nameDisplay: displayName,
        job: dataset.job || item.querySelector('.id-card-field:nth-child(1) .id-card-value')?.textContent?.trim() || '',
        importance: parseFloat(dataset.importance) || 0,
        docCount: parseInt(dataset.docCount, 10) || 0,
        country: dataset.country || '',
        countryLabel: dataset.countryLabel || dataset.country || '',
        city: dataset.city || '',
        cityLabel: dataset.cityLabel || dataset.city || '',
        ownership: dataset.ownership || '',
        ownershipLabel: dataset.ownershipLabel || dataset.ownership || '',
        accessStatus: dataset.accessStatus || '',
        accessStatusLabel: dataset.accessStatusLabel || dataset.accessStatus || '',
        categoryId: dataset.categoryId || '',
        categoryName: dataset.categoryName || '',
        discoveryDate: dataset.discoveryDate || '',
        element: item
    };
}

function normalizeSourceRecord(source) {
    const displayName = source.nameDisplay || source.name || '';
    return {
        id: String(source.id || '').trim(),
        name: String(displayName).toLowerCase(),
        nameDisplay: displayName,
        job: source.job || '',
        importance: Number.isFinite(Number(source.importance)) ? Number(source.importance) : 0.5,
        docCount: Number.isFinite(Number(source.docCount)) ? Number(source.docCount) : 0,
        country: String(source.country || source.countryLabel || '').toLowerCase(),
        countryLabel: source.countryLabel || source.country || '',
        city: String(source.city || source.cityLabel || '').toLowerCase(),
        cityLabel: source.cityLabel || source.city || '',
        ownership: String(source.ownership || source.ownershipLabel || '').toLowerCase(),
        ownershipLabel: source.ownershipLabel || source.ownership || '',
        accessStatus: String(source.accessStatus || source.accessStatusLabel || '').toLowerCase(),
        accessStatusLabel: source.accessStatusLabel || source.accessStatus || '',
        categoryId: source.categoryId || '',
        categoryName: source.categoryName || '',
        discoveryDate: source.discoveryDate || '',
        element: source.element || null
    };
}

function formatImportance(value) {
    const numeric = Math.max(0, Math.min(1, Number(value) || 0));
    return `${Math.round(numeric * 100)}%`;
}

function renderStars(value) {
    const stars = Math.round((Number(value) || 0) * 5);
    let html = '';
    for (let i = 0; i < 5; i += 1) {
        html += `<i class="bi ${i < stars ? 'bi-star-fill text-warning' : 'bi-star text-muted'}"></i>`;
    }
    return html;
}

function locationLabel(source) {
    if (source.cityLabel && source.countryLabel) return `${source.cityLabel}, ${source.countryLabel}`;
    return source.cityLabel || source.countryLabel || '—';
}

function sourceActions(source, compact = false) {
    const id = escapeAttr(source.id);
    const nameJson = escapeAttr(JSON.stringify(source.nameDisplay || ''));
    const viewLabel = translations.viewDetails || translations.view || 'View';
    const label = compact ? '' : ` <span class="d-none d-xl-inline">${escapeHtml(viewLabel)}</span>`;
    return `
        <div class="btn-group btn-group-sm ia-action-group" role="group" aria-label="${escapeAttr(translations.sourceActions || 'Source actions')}">
            <button class="btn btn-outline-primary" onclick="viewSource('${id}')" title="${escapeAttr(viewLabel)}"><i class="bi bi-eye"></i>${label}</button>
            <button class="btn btn-outline-success" onclick="editSource('${id}')" title="${escapeAttr(translations.editSource || 'Edit source')}"><i class="bi bi-pencil"></i></button>
            <button class="btn btn-outline-info" onclick="duplicateSource('${id}')" title="${escapeAttr(translations.duplicateSource || 'Duplicate source')}"><i class="bi bi-files"></i></button>
            <button class="btn btn-outline-secondary" onclick="exportSource('${id}')" title="${escapeAttr(translations.exportData || 'Export data')}"><i class="bi bi-download"></i></button>
            <button class="btn btn-outline-primary" onclick="viewSourceCategoriesKeywords('${id}')" title="${escapeAttr(translations.viewCategoriesKeywords || 'View categories and keywords')}"><i class="bi bi-tags"></i></button>
            <button class="btn btn-outline-danger" onclick='deleteSource("${id}", ${nameJson})' title="${escapeAttr(translations.deleteSource || 'Delete source')}"><i class="bi bi-trash"></i></button>
        </div>`;
}

function createSourceCard(source) {
    const card = document.createElement('div');
    card.className = 'col-md-6 col-lg-4 col-xl-3 source-card-item';
    card.dataset.name = source.name;
    card.dataset.displayName = source.nameDisplay;
    card.dataset.job = source.job || '';
    card.dataset.importance = source.importance;
    card.dataset.docCount = source.docCount;
    card.dataset.id = source.id;
    card.dataset.country = source.country || '';
    card.dataset.countryLabel = source.countryLabel || '';
    card.dataset.city = source.city || '';
    card.dataset.cityLabel = source.cityLabel || '';
    card.dataset.ownership = source.ownership || '';
    card.dataset.ownershipLabel = source.ownershipLabel || '';
    card.dataset.accessStatus = source.accessStatus || '';
    card.dataset.accessStatusLabel = source.accessStatusLabel || '';
    card.dataset.categoryId = source.categoryId || '';
    card.dataset.categoryName = source.categoryName || '';
    card.dataset.discoveryDate = source.discoveryDate || '';
    card.innerHTML = `
        <div class="id-card ia-record-card">
            <div class="id-card-header">
                <div class="id-card-icon"><i class="bi bi-building"></i></div>
                <div class="id-card-id"><span class="badge bg-secondary">#${escapeHtml(source.id)}</span></div>
            </div>
            <div class="id-card-body">
                <h3 class="id-card-name">${escapeHtml(source.nameDisplay)}</h3>
                <div class="id-card-info">
                    <div class="id-card-field"><i class="bi bi-briefcase text-muted"></i><span class="id-card-label">${escapeHtml(translations.jobType || 'Job/Type')}:</span><span class="id-card-value">${escapeHtml(source.job || '—')}</span></div>
                    <div class="id-card-field"><i class="bi bi-geo-alt text-muted"></i><span class="id-card-label">${escapeHtml(translations.location || 'Location')}:</span><span class="id-card-value">${escapeHtml(locationLabel(source))}</span></div>
                    <div class="id-card-field"><i class="bi bi-star text-muted"></i><span class="id-card-label">${escapeHtml(translations.importance || 'Importance')}:</span><div class="id-card-stars">${renderStars(source.importance)}<span class="ms-2 text-muted">(${formatImportance(source.importance)})</span></div></div>
                    <div class="id-card-field"><i class="bi bi-file-earmark text-muted"></i><span class="id-card-label">${escapeHtml(translations.documents || 'Documents')}:</span><span class="badge bg-primary">${source.docCount}</span></div>
                    ${source.ownershipLabel ? `<div class="id-card-field"><i class="bi bi-shield-check text-muted"></i><span class="id-card-label">${escapeHtml(translations.ownership || 'Ownership')}:</span><span class="id-card-value">${escapeHtml(source.ownershipLabel)}</span></div>` : ''}
                    ${source.accessStatusLabel ? `<div class="id-card-field"><i class="bi bi-lock text-muted"></i><span class="id-card-label">${escapeHtml(translations.access || 'Access')}:</span><span class="badge bg-info">${escapeHtml(source.accessStatusLabel)}</span></div>` : ''}
                    ${source.categoryName ? `<div class="id-card-field"><i class="bi bi-tags text-muted"></i><span class="id-card-label">${escapeHtml(translations.category || 'Category')}:</span><span class="badge bg-success">${escapeHtml(source.categoryName)}</span></div>` : ''}
                    ${source.discoveryDate ? `<div class="id-card-field"><i class="bi bi-calendar-event text-muted"></i><span class="id-card-label">${escapeHtml(translations.discovery || 'Discovery')}:</span><span class="id-card-value">${escapeHtml(source.discoveryDate.slice(0, 10))}</span></div>` : ''}
                </div>
            </div>
            <div class="id-card-footer">
                <div class="d-flex align-items-center mb-2">
                    <input type="checkbox" class="form-check-input source-checkbox me-2" value="${escapeAttr(source.id)}" onchange="updateBulkButtons()" aria-label="Select source: ${escapeAttr(source.nameDisplay)}">
                    <small class="text-muted">${escapeHtml(translations.select || 'Select')}</small>
                </div>
                ${sourceActions(source, true)}
            </div>
        </div>`;
    return card;
}

function ensureStructuredViews() {
    const grid = getRecordContainer();
    if (!grid || !grid.parentElement) return {};
    let tableView = document.getElementById('sourcesTableView');
    let listView = document.getElementById('sourcesListView');
    if (!tableView) {
        tableView = document.createElement('div');
        tableView.id = 'sourcesTableView';
        tableView.className = 'sources-structured-view d-none';
        grid.parentElement.insertBefore(tableView, grid.nextSibling);
    }
    if (!listView) {
        listView = document.createElement('div');
        listView.id = 'sourcesListView';
        listView.className = 'sources-structured-view ia-record-list d-none';
        grid.parentElement.insertBefore(listView, tableView.nextSibling);
    }
    return { grid, tableView, listView };
}

function renderSourcesTable(records) {
    const { tableView } = ensureStructuredViews();
    if (!tableView) return;
    tableView.innerHTML = `
        <div class="table-wrapper sources-table-wrapper">
            <table class="table table-hover align-middle sources-table" id="sourcesTable" data-ia-table="sources" data-ia-sort="true">
                <thead>
                    <tr>
                        <th style="width:44px"><input type="checkbox" onchange="this.closest('table').querySelectorAll('.source-checkbox').forEach(cb => cb.checked = this.checked); updateBulkButtons();"></th>
                        <th>ID</th><th>${escapeHtml(translations.source || 'Source')}</th><th>${escapeHtml(translations.jobType || 'Job/Type')}</th><th>${escapeHtml(translations.importance || 'Importance')}</th><th>${escapeHtml(translations.documents || 'Documents')}</th><th>${escapeHtml(translations.location || 'Location')}</th><th>${escapeHtml(translations.access || 'Access')}</th><th>${escapeHtml(translations.category || 'Category')}</th><th>${escapeHtml(translations.actions || 'Actions')}</th>
                    </tr>
                </thead>
                <tbody>
                    ${records.map(source => `
                        <tr data-source-id="${escapeAttr(source.id)}">
                            <td><input type="checkbox" class="form-check-input source-checkbox" value="${escapeAttr(source.id)}" onchange="updateBulkButtons()"></td>
                            <td><span class="badge bg-secondary">#${escapeHtml(source.id)}</span></td>
                            <td><strong title="${escapeAttr(source.nameDisplay)}">${escapeHtml(source.nameDisplay)}</strong></td>
                            <td>${escapeHtml(source.job || '—')}</td>
                            <td data-sort-value="${Number(source.importance) || 0}"><span class="badge bg-primary">${formatImportance(source.importance)}</span></td>
                            <td data-sort-value="${source.docCount}"><span class="badge bg-info">${source.docCount}</span></td>
                            <td title="${escapeAttr(locationLabel(source))}">${escapeHtml(locationLabel(source))}</td>
                            <td>${source.accessStatusLabel ? `<span class="badge bg-info">${escapeHtml(source.accessStatusLabel)}</span>` : '—'}</td>
                            <td>${source.categoryName ? `<span class="badge bg-success">${escapeHtml(source.categoryName)}</span>` : '—'}</td>
                            <td>${sourceActions(source, true)}</td>
                        </tr>`).join('')}
                </tbody>
            </table>
        </div>`;
}

function renderSourcesList(records) {
    const { listView } = ensureStructuredViews();
    if (!listView) return;
    listView.innerHTML = records.map(source => `
        <div class="ia-record-list-row source-card-item" data-id="${escapeAttr(source.id)}" data-name="${escapeAttr(source.name)}">
            <div class="d-flex flex-wrap justify-content-between align-items-center gap-2">
                <div class="min-w-0">
                    <div class="d-flex align-items-center gap-2">
                        <span class="badge bg-secondary">#${escapeHtml(source.id)}</span>
                        <strong class="ia-truncate" title="${escapeAttr(source.nameDisplay)}">${escapeHtml(source.nameDisplay)}</strong>
                        <span class="badge bg-primary">${formatImportance(source.importance)}</span>
                    </div>
                    <div class="small text-muted mt-1">${escapeHtml(source.job || '—')} · ${escapeHtml(locationLabel(source))} · ${source.docCount} ${escapeHtml((translations.documents || 'documents').toLowerCase())}</div>
                </div>
                ${sourceActions(source, true)}
            </div>
        </div>`).join('');
}

function renderCurrentFormat() {
    const { grid, tableView, listView } = ensureStructuredViews();
    if (!grid) return;

    grid.classList.toggle('d-none', currentFormat !== 'grid');
    if (tableView) tableView.classList.toggle('d-none', currentFormat !== 'table');
    if (listView) listView.classList.toggle('d-none', currentFormat !== 'list');

    if (currentFormat === 'grid') {
        filteredSources.forEach((source, index) => {
            if (!source.element) {
                source.element = createSourceCard(source);
                grid.appendChild(source.element);
            }
            source.element.style.display = '';
            source.element.style.order = index;
        });
        allSources.forEach(source => {
            if (!filteredSources.includes(source) && source.element) source.element.style.display = 'none';
        });
    } else {
        allSources.forEach(source => {
            if (source.element) source.element.style.display = 'none';
        });
        if (currentFormat === 'table') renderSourcesTable(filteredSources);
        if (currentFormat === 'list') renderSourcesList(filteredSources);
    }

    window.InforaxisDataInterface?.refresh(grid.parentElement || document);
}

function upsertSourceRecord(source, highlight = true) {
    const normalized = normalizeSourceRecord(source);
    const index = allSources.findIndex(item => String(item.id) === String(normalized.id));
    if (index >= 0) {
        normalized.element = allSources[index].element;
        if (normalized.element) {
            const replacement = createSourceCard(normalized);
            normalized.element.replaceWith(replacement);
            normalized.element = replacement;
        }
        allSources[index] = normalized;
    } else {
        normalized.element = createSourceCard(normalized);
        getRecordContainer()?.appendChild(normalized.element);
        allSources.unshift(normalized);
    }
    applyFilters();
    if (highlight) {
        const selector = currentFormat === 'table'
            ? `#sourcesTable tr[data-source-id="${CSS.escape(String(normalized.id))}"]`
            : currentFormat === 'list'
                ? `#sourcesListView [data-id="${CSS.escape(String(normalized.id))}"]`
                : normalized.element;
        window.InforaxisDataInterface?.highlightNewRecord(selector);
    }
}

function removeSourceRecord(sourceId) {
    const index = allSources.findIndex(item => String(item.id) === String(sourceId));
    if (index >= 0) {
        const [removed] = allSources.splice(index, 1);
        removed.element?.remove();
    }
    document.querySelectorAll(`[data-source-id="${CSS.escape(String(sourceId))}"], .source-card-item[data-id="${CSS.escape(String(sourceId))}"]`).forEach(el => el.remove());
    applyFilters();
    updateBulkButtons();
}

// Initialize sources data from DOM
function initializeSourcesData() {
    const sourceItems = document.querySelectorAll('.source-card-item[data-id]');
    const map = new Map();

    sourceItems.forEach(item => {
        const source = sourceFromElement(item);
        if (source.id && !map.has(source.id)) {
            map.set(source.id, source);
        }
    });

    allSources = Array.from(map.values());
    filteredSources = [...allSources];

    const formatSelect = document.getElementById('displayFormat');
    const storage = safeLocalStorageRef();
    const savedFormat = storage?.getItem('inforaxis.sources.displayFormat');
    if (formatSelect && savedFormat && Array.from(formatSelect.options).some(option => option.value === savedFormat)) {
        currentFormat = savedFormat;
        formatSelect.value = savedFormat;
    } else if (formatSelect) {
        currentFormat = formatSelect.value || currentFormat;
    }

    ensureStructuredViews();
    updateStats();
}

// Update statistics
function updateStats() {
    const totalCount = allSources.length;
    const filteredCount = filteredSources.length;
    const visibleCount = filteredSources.length;

    const totalEl = document.getElementById('totalSourcesCount');
    const filteredEl = document.getElementById('filteredSourcesCount');
    const visibleEl = document.getElementById('visibleSourcesCount');
    const pageEl = document.getElementById('currentPageInfo');

    if (totalEl) totalEl.textContent = totalCount.toLocaleString();
    if (filteredEl) filteredEl.textContent = filteredCount.toLocaleString();
    if (visibleEl) visibleEl.textContent = visibleCount.toLocaleString();
    if (pageEl && filteredCount <= allSources.length) pageEl.textContent = `1 / ${Math.max(1, Math.ceil(filteredCount / Math.max(1, itemsPerPage)))}`;
}

// Apply filters and sorting
function applyFilters() {
    const searchInput = document.getElementById('sourceSearch');
    const sortBy = document.getElementById('sortBy');

    const searchTerm = (searchInput?.value || '').toLowerCase().trim();
    currentSort = sortBy?.value || 'importance-desc';

    filteredSources = allSources.filter(source => {
        if (!searchTerm) return true;
        return [source.name, source.nameDisplay, source.job, source.countryLabel, source.cityLabel, source.ownershipLabel, source.accessStatusLabel, source.categoryName]
            .join(' ')
            .toLowerCase()
            .includes(searchTerm);
    });

    const [sortField, sortDirection] = currentSort.split('-');
    filteredSources.sort((a, b) => {
        let aVal;
        let bVal;

        switch (sortField) {
            case 'name':
                aVal = a.nameDisplay || a.name || '';
                bVal = b.nameDisplay || b.name || '';
                break;
            case 'importance':
                aVal = a.importance || 0;
                bVal = b.importance || 0;
                break;
            case 'id':
                aVal = parseInt(a.id, 10) || 0;
                bVal = parseInt(b.id, 10) || 0;
                break;
            case 'doc_count':
                aVal = a.docCount || 0;
                bVal = b.docCount || 0;
                break;
            default:
                aVal = a.nameDisplay || a.name || '';
                bVal = b.nameDisplay || b.name || '';
        }

        const result = typeof aVal === 'number' && typeof bVal === 'number'
            ? aVal - bVal
            : String(aVal).localeCompare(String(bVal), undefined, { numeric: true, sensitivity: 'base' });
        return sortDirection === 'asc' ? result : -result;
    });

    renderCurrentFormat();
    updateStats();
}

// Change display format
function changeDisplayFormat() {
    const formatSelect = document.getElementById('displayFormat');
    if (!formatSelect) return;

    currentFormat = formatSelect.value || 'grid';
    safeLocalStorageRef()?.setItem('inforaxis.sources.displayFormat', currentFormat);
    renderCurrentFormat();
    updateBulkButtons();
}

// Change page size
function changePageSize() {
    const itemsPerPageSelect = document.getElementById('itemsPerPage');
    if (!itemsPerPageSelect) return;
    
    const newLimit = parseInt(itemsPerPageSelect.value) || 50;
    itemsPerPage = newLimit;
    
    // Update URL with new limit parameter and reset to first page
    const url = new URL(window.location.href);
    url.searchParams.set('limit', newLimit);
    url.searchParams.delete('cursor'); // Reset to first page
    url.searchParams.delete('page');
    window.location.href = url.toString();
}

// Selection management
function getActiveSourcesContainer() {
    return currentFormat === 'table'
        ? document.getElementById('sourcesTableView')
        : currentFormat === 'list'
            ? document.getElementById('sourcesListView')
            : document.getElementById('sourcesCardContainer');
}

function getSelectedSourceIds() {
    const activeContainer = getActiveSourcesContainer();
    const checkboxes = activeContainer ? activeContainer.querySelectorAll('.source-checkbox:checked') : document.querySelectorAll('.source-checkbox:checked');
    return Array.from(new Set(Array.from(checkboxes).map(cb => parseInt(cb.value, 10)).filter(Boolean)));
}

function selectAll() {
    const activeContainer = getActiveSourcesContainer();
    const checkboxes = activeContainer ? activeContainer.querySelectorAll('.source-checkbox') : document.querySelectorAll('.source-checkbox');
    checkboxes.forEach(cb => { cb.checked = true; });
    updateBulkButtons();
}

function selectNone() {
    document.querySelectorAll('.source-checkbox').forEach(cb => { cb.checked = false; });
    updateBulkButtons();
}

function updateBulkButtons() {
    const hasSelection = getSelectedSourceIds().length > 0;

    const bulkExportBtn = document.getElementById('bulkExportBtn');
    const bulkUpdateBtn = document.getElementById('bulkUpdateBtn');

    if (bulkExportBtn) bulkExportBtn.disabled = !hasSelection;
    if (bulkUpdateBtn) bulkUpdateBtn.disabled = !hasSelection;
}

// Bulk operations
function bulkExport() {
    const selectedIds = getSelectedSourceIds();
    
    if (selectedIds.length === 0) {
        showToast('Please select sources to export', 'warning');
        return;
    }
    
    // Export functionality - would need backend endpoint
    showToast(`Exporting ${selectedIds.length} source(s)...`, 'info');
    console.log('Bulk export:', selectedIds);
}

function bulkUpdate() {
    const selectedIds = getSelectedSourceIds();
    
    if (selectedIds.length === 0) {
        showToast('Please select sources to update', 'warning');
        return;
    }
    
    // Bulk update functionality - would need backend endpoint
    showToast(`Updating ${selectedIds.length} source(s)...`, 'info');
    console.log('Bulk update:', selectedIds);
}

// Clear search
function clearSearch() {
    const searchInput = document.getElementById('sourceSearch');
    if (searchInput) {
        searchInput.value = '';
        applyFilters();
    }
}

// View source categories and keywords
function viewSourceCategoriesKeywords(sourceId) {
    window.location.href = `/sources/${sourceId}/categories-keywords`;
}

// View source details
function viewSource(sourceId) {
    window.location.href = `/sources/${sourceId}`;
}

// Edit source
function editSource(sourceId) {
    openSourceModal(sourceId);
}

// Initialize event listeners
function initializeEventListeners() {
    const searchInput = document.getElementById('sourceSearch');
    if (searchInput) {
        searchInput.addEventListener('input', debounce(() => {
            applyFilters();
        }, 300));
    }
    
    const sortBy = document.getElementById('sortBy');
    if (sortBy) {
        sortBy.addEventListener('change', () => {
            applyFilters();
        });
    }
    
    const displayFormat = document.getElementById('displayFormat');
    if (displayFormat) {
        displayFormat.addEventListener('change', () => {
            changeDisplayFormat();
        });
    }
    
    const itemsPerPageSelect = document.getElementById('itemsPerPage');
    if (itemsPerPageSelect) {
        itemsPerPageSelect.addEventListener('change', () => {
            changePageSize();
        });
    }
    
    // Checkbox change listeners
    document.addEventListener('change', (e) => {
        if (e.target.classList.contains('source-checkbox')) {
            updateBulkButtons();
        }
    });
}

// Initialize on DOM ready
document.addEventListener('DOMContentLoaded', function() {
    initializeSourcesData();
    initializeEventListeners();
    applyFilters();
});

// Make functions globally accessible IMMEDIATELY (before module loads)
// This ensures buttons work even if module hasn't finished loading
window.selectAll = selectAll;
window.selectNone = selectNone;
window.updateBulkButtons = updateBulkButtons;
window.bulkExport = bulkExport;
window.bulkUpdate = bulkUpdate;
window.clearSearch = clearSearch;
window.applyFilters = applyFilters;
window.changeDisplayFormat = changeDisplayFormat;
window.changePageSize = changePageSize;
window.viewSourceCategoriesKeywords = viewSourceCategoriesKeywords;
window.viewSource = viewSource;
window.editSource = editSource;



// ✅ SECURITY: Helper function to get CSRF token
function getCSRFToken() {
    const metaTag = document.querySelector('meta[name="csrf-token"]');
    return metaTag ? metaTag.getAttribute('content') : '';
}

function duplicateSource(sourceId) {
    if (confirm(translations.createCopyOfSource)) {
        fetch(`/api/sources/${sourceId}/duplicate`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCSRFToken()
            }
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                const original = allSources.find(source => String(source.id) === String(sourceId));
                if (original && data.new_source_id) {
                    const duplicated = normalizeSourceRecord({
                        ...original,
                        id: data.new_source_id,
                        name: data.new_name || `${original.nameDisplay} (Copy)`,
                        nameDisplay: data.new_name || `${original.nameDisplay} (Copy)`,
                        docCount: 0,
                        element: null
                    });
                    upsertSourceRecord(duplicated, true);
                } else {
                    setTimeout(() => {
                        window.location.href = window.location.pathname + '?t=' + Date.now();
                    }, 500);
                }
                showToast(translations.sourceDuplicatedSuccessfully || 'Source duplicated successfully!', 'success');
            } else {
                showToast((translations.errorDuplicatingSource || 'Error duplicating source') + ': ' + (data.message || (translations.unknownError || 'Unknown error')), 'error');
            }
        })
        .catch(error => {
            console.error('Error:', error);
            showToast(translations.errorDuplicatingSource || 'Error duplicating source', 'error');
        });
    }
}

function toggleSourceStatus(sourceId) {
    fetch(`/api/sources/${sourceId}/toggle-status`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': getCSRFToken()
        }
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showToast(translations.sourceStatusUpdated || 'Source status updated!', 'success');
            setTimeout(() => {
                window.location.href = window.location.pathname + '?t=' + Date.now();
            }, 500);
        } else {
            showToast((translations.errorUpdatingStatus || 'Error updating status') + ': ' + (data.message || (translations.unknownError || 'Unknown error')), 'error');
        }
    })
    .catch(error => {
        console.error('Error:', error);
        showToast(translations.errorUpdatingSourceStatus || 'Error updating source status', 'error');
    });
}

function exportSource(sourceId) {
    fetch(`/api/sources/${sourceId}/export`, {
        method: 'GET',
    })
    .then(response => {
        if (response.ok) {
            return response.blob();
        }
        throw new Error('Export failed');
    })
    .then(blob => {
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `source_${sourceId}_export.json`;
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(url);
        document.body.removeChild(a);
        showToast(translations.sourceDataExportedSuccessfully || 'Source data exported successfully!', 'success');
    })
    .catch(error => {
        console.error('Error:', error);
        showToast(translations.errorExportingSourceData || 'Error exporting source data', 'error');
    });
}

function deleteSource(sourceId, sourceName = '') {
    const confirmMessage = sourceName 
        ? `${translations.areYouSureDeleteSource || 'Are you sure you want to delete the source'} "${sourceName}"?\n\n${translations.actionCannotBeUndone || 'This action cannot be undone.'}`
        : translations.deleteSourceConfirm;
    
    // Show confirmation modal
    const modal = new bootstrap.Modal(document.getElementById('deleteConfirmModal'));
    const messageEl = document.getElementById('deleteConfirmMessage');
    const confirmBtn = document.getElementById('deleteConfirmButton');
    
    messageEl.textContent = confirmMessage;
    
    // Remove any existing event listeners
    const newConfirmBtn = confirmBtn.cloneNode(true);
    confirmBtn.parentNode.replaceChild(newConfirmBtn, confirmBtn);
    
    // Add click handler for confirmation
    newConfirmBtn.addEventListener('click', function performDelete() {
        modal.hide();
        
        // Show processing notification
        if (window.MessageFormatter) {
            window.MessageFormatter.showNotification('delete', 'processing', { item: sourceName || 'Source' });
        }
        
        fetch(`/api/sources/${sourceId}`, {
            method: 'DELETE',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCSRFToken()
            }
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                // Show formatted success notification
                if (window.MessageFormatter) {
                    window.MessageFormatter.showDeleteSuccess(sourceName || 'Source', {
                        title: translations.sourceDeleted || 'Source Deleted',
                        duration: 4000
                    });
                } else {
                    showToast(translations.sourceDeletedSuccessfully || 'Source deleted successfully!', 'success');
                }
                removeSourceRecord(sourceId);
            } else {
                // Show formatted error notification
                if (window.MessageFormatter) {
                    window.MessageFormatter.showDeleteError(sourceName || 'Source', {
                        title: translations.deleteFailed || 'Delete Failed',
                        duration: 6000
                    });
                } else {
                    showToast((translations.errorDeletingSource || 'Error deleting source') + ': ' + (data.error || (translations.unknownError || 'Unknown error')), 'error');
                }
            }
        })
        .catch(error => {
            console.error('Error:', error);
            if (window.MessageFormatter) {
                window.MessageFormatter.showDeleteError(sourceName || 'Source', {
                    title: translations.deleteError || 'Delete Error',
                    duration: 6000
                });
            } else {
                showToast(translations.errorDeletingSource || 'Error deleting source', 'error');
            }
        });
    });
    
    modal.show();
}

// Modal functions
let categories = [];

function openSourceModal(sourceId = null) {
    const modal = new bootstrap.Modal(document.getElementById('sourceModal'));
    const form = document.getElementById('sourceForm');
    const modalTitle = document.getElementById('modalTitle');
    const submitButtonText = document.getElementById('submitButtonText');
    
    // Reset form
    form.reset();
    document.getElementById('sourceId').value = '';
    document.getElementById('importanceSlider').value = '0.5';
    document.getElementById('importanceValue').textContent = '0.50';
    
    if (sourceId) {
        // Edit mode
        modalTitle.textContent = translations.editSource || 'Edit Source';
        submitButtonText.textContent = translations.updateSource || 'Update Source';
        document.getElementById('modalIcon').className = 'bi bi-pencil me-2';
        document.getElementById('sourceId').value = sourceId;
        
        // Load source data
        fetch(`/api/sources/${sourceId}`)
            .then(response => {
                if (!response.ok) {
                    return response.json().then(err => {
                        throw new Error(err.error || `HTTP error! status: ${response.status}`);
                    });
                }
                return response.json();
            })
            .then(data => {
                if (data.success && data.source) {
                    const source = data.source;
                    document.getElementById('sourceName').value = source.name || '';
                    document.getElementById('sourceJob').value = source.job || '';
                    document.getElementById('sourceCountry').value = source.country || '';
                    document.getElementById('sourceCity').value = source.city || '';
                    document.getElementById('sourceDescription').value = source.description || '';
                    document.getElementById('sourceAccounts').value = source.accounts || '';
                    document.getElementById('sourceAttachments').value = source.attachments || '';
                    document.getElementById('sourceNote').value = source.note || '';
                    
                    // Set enum/optional fields - handle null values properly
                    const ownershipValue = source.ownership ? source.ownership : '';
                    document.getElementById('sourceOwnership').value = ownershipValue;
                    
                    const accessStatusValue = source.access_status ? source.access_status : '';
                    document.getElementById('sourceAccessStatus').value = accessStatusValue;
                    
                    // Category needs to be set after categories are loaded
                    const categoryId = source.category_id ? source.category_id.toString() : '';
                    // Store category ID to set after categories load
                    if (categories.length > 0) {
                        populateCategoryDropdown(categoryId);
                    } else {
                        // If categories not loaded yet, wait for them to load
                        const checkCategories = setInterval(() => {
                            if (categories.length > 0) {
                                clearInterval(checkCategories);
                                populateCategoryDropdown(categoryId);
                            }
                        }, 100);
                        // Timeout after 2 seconds
                        setTimeout(() => clearInterval(checkCategories), 2000);
                    }
                    
                    // Date field - handle null/empty values
                    if (source.date_source_discovery) {
                        try {
                            const date = new Date(source.date_source_discovery);
                            if (!isNaN(date.getTime())) {
                                document.getElementById('sourceDateDiscovery').value = date.toISOString().split('T')[0];
                            } else {
                                document.getElementById('sourceDateDiscovery').value = '';
                            }
                        } catch (e) {
                            console.warn('Error parsing date:', e);
                            document.getElementById('sourceDateDiscovery').value = '';
                        }
                    } else {
                        document.getElementById('sourceDateDiscovery').value = '';
                    }
                    
                    const importance = source.importance || 0.5;
                    document.getElementById('importanceSlider').value = importance;
                    document.getElementById('importanceValue').textContent = parseFloat(importance).toFixed(2);
                } else {
                    showToast((translations.errorLoadingSource || 'Error loading source') + ': ' + (data.error || (translations.unknownError || 'Unknown error')), 'error');
                    modal.hide();
                }
            })
            .catch(error => {
                console.error('Error loading source data:', error);
                showToast(translations.errorLoadingSourceData || 'Error loading source data: ' + error.message, 'error');
                modal.hide();
            });
    } else {
        // Add mode
        modalTitle.textContent = translations.addNewSource || 'Add New Source';
        submitButtonText.textContent = translations.createSource || 'Create Source';
        document.getElementById('modalIcon').className = 'bi bi-plus-circle me-2';
    }
    
    // Load categories if not already loaded
    if (categories.length === 0) {
        loadCategories();
    } else {
        populateCategoryDropdown();
    }
    
    modal.show();
}

function loadCategories() {
    fetch('/api/categories')
        .then(response => response.json())
        .then(data => {
            categories = Array.isArray(data) ? data : [];
            populateCategoryDropdown();
        })
        .catch(error => {
            console.error('Error loading categories:', error);
            categories = [];
        });
}

function populateCategoryDropdown(preserveValue = null) {
    const categorySelect = document.getElementById('sourceCategory');
    const currentValue = preserveValue !== null ? preserveValue : categorySelect.value;
    
    // Clear existing options except the first one
    categorySelect.innerHTML = `<option value="">-- ${translations.selectCategory || 'Select Category'} --</option>`;
    
    categories.forEach(cat => {
        const option = document.createElement('option');
        option.value = cat.id;
        option.textContent = cat.name;
        categorySelect.appendChild(option);
    });
    
    // Restore previous selection if provided or if in edit mode
    if (currentValue) {
        categorySelect.value = currentValue;
    }
}

async function submitSourceForm() {
    const form = document.getElementById('sourceForm');
    const sourceId = document.getElementById('sourceId').value;
    const submitButton = document.querySelector('#sourceModal .modal-footer .btn-primary');
    const formData = new FormData(form);

    if (!formData.get('name') || !formData.get('job') || !formData.get('country')) {
        form.classList.add('was-validated');
        showToast(translations.pleaseFillInAllRequiredFields || 'Please fill in all required fields (Name, Job/Type, Country)', 'warning');
        return;
    }

    const data = {
        name: formData.get('name') || '',
        job: formData.get('job') || '',
        country: formData.get('country') || '',
        city: formData.get('city') || '',
        importance: parseFloat(formData.get('importance')) || 0.5,
        description: formData.get('description') || '',
        accounts: formData.get('accounts') || '',
        note: formData.get('note') || '',
        attachments: formData.get('attachments') || '',
        ownership: (() => {
            const val = formData.get('ownership');
            return (val && val.trim()) ? val : null;
        })(),
        access_status: (() => {
            const val = formData.get('access_status');
            return (val && val.trim()) ? val : null;
        })(),
        date_source_discovery: (() => {
            const val = formData.get('date_source_discovery');
            return (val && val.trim()) ? val : null;
        })(),
        category_id: (() => {
            const val = formData.get('category_id');
            if (val && val.trim()) {
                const num = parseInt(val, 10);
                return Number.isNaN(num) ? null : num;
            }
            return null;
        })()
    };

    const url = sourceId ? `/api/sources/${sourceId}` : '/api/sources';
    const method = sourceId ? 'PUT' : 'POST';
    const sourceName = data.name || 'Source';
    const isEdit = !!sourceId;

    window.InforaxisDataInterface?.setButtonBusy(submitButton, true, {
        label: isEdit ? (translations.updateSource || 'Update Source') : (translations.createSource || 'Create Source')
    });

    try {
        const response = await fetch(url, {
            method: method,
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCSRFToken()
            },
            body: JSON.stringify(data)
        });
        const result = await response.json().catch(() => ({}));
        if (!response.ok || result.success === false) {
            throw new Error(result.error || `HTTP error! status: ${response.status}`);
        }

        if (window.MessageFormatter && typeof window.MessageFormatter.showCreateSuccess === 'function') {
            if (isEdit) {
                window.MessageFormatter.showUpdateSuccess(sourceName, { title: 'Source Updated', duration: 4000 });
            } else {
                window.MessageFormatter.showCreateSuccess(sourceName, { title: 'Source Created', duration: 4000 });
            }
        } else {
            showToast(
                isEdit ? (translations.sourceUpdatedSuccessfully || 'Source updated successfully!') : (translations.sourceCreatedSuccessfully || 'Source created successfully!'),
                'success'
            );
        }

        const categorySelect = document.getElementById('sourceCategory');
        const savedId = String(sourceId || result.id || result.source?.id || result.source_id || '');
        if (savedId) {
            const existing = allSources.find(item => String(item.id) === savedId);
            upsertSourceRecord({
                id: savedId,
                nameDisplay: sourceName,
                job: data.job,
                importance: data.importance,
                docCount: existing?.docCount || 0,
                country: data.country,
                countryLabel: data.country,
                city: data.city,
                cityLabel: data.city,
                ownership: data.ownership || '',
                ownershipLabel: data.ownership || '',
                accessStatus: data.access_status || '',
                accessStatusLabel: data.access_status || '',
                categoryId: data.category_id || '',
                categoryName: data.category_id ? (categorySelect?.selectedOptions?.[0]?.textContent || '').replace(/^--|--$/g, '').trim() : '',
                discoveryDate: data.date_source_discovery || '',
                element: existing?.element || null
            }, true);
        } else {
            window.location.href = window.location.pathname + '?t=' + Date.now();
        }

        bootstrap.Modal.getInstance(document.getElementById('sourceModal'))?.hide();
        form.reset();
    } catch (error) {
        console.error('Error saving source:', error);
        if (window.MessageFormatter && typeof window.MessageFormatter.showCreateError === 'function') {
            if (isEdit) {
                window.MessageFormatter.showUpdateError(sourceName, { title: 'Update Error', duration: 6000 });
            } else {
                window.MessageFormatter.showCreateError(sourceName, { title: 'Create Error', duration: 6000 });
            }
        } else {
            showToast((translations.errorSavingSource || 'Error saving source') + ': ' + error.message, 'error');
        }
    } finally {
        window.InforaxisDataInterface?.setButtonBusy(submitButton, false);
    }
}

// Make functions globally accessible for onclick handlers
// Export immediately (not in DOMContentLoaded) so they're available when buttons are clicked
// This IIFE runs as soon as the module loads, ensuring functions are available immediately
(function() {
    // Export all button handler functions to window object
    // This ensures they're available even if the module hasn't fully initialized
    window.viewSource = viewSource;
    window.editSource = editSource;
    window.duplicateSource = duplicateSource;
    window.toggleSourceStatus = toggleSourceStatus;
    window.exportSource = exportSource;
    window.deleteSource = deleteSource;
    window.openSourceModal = openSourceModal;
    window.submitSourceForm = submitSourceForm;
    window.viewSourceCategoriesKeywords = viewSourceCategoriesKeywords;
    
    // Remove retry wrapper flags if they exist
    Object.keys(window).forEach(key => {
        if (window[key] && window[key]._isRetryWrapper) {
            delete window[key]._isRetryWrapper;
        }
    });
})();

// Initialize importance slider
document.addEventListener('DOMContentLoaded', function() {
    const slider = document.getElementById('importanceSlider');
    const valueDisplay = document.getElementById('importanceValue');
    
    if (slider && valueDisplay) {
        slider.addEventListener('input', (e) => {
            valueDisplay.textContent = parseFloat(e.target.value).toFixed(2);
        });
    }
    
    // Check if we should open the modal in edit mode from URL parameter
    const urlParams = new URLSearchParams(window.location.search);
    const editId = urlParams.get('edit');
    if (editId) {
        // Remove the edit parameter from URL
        urlParams.delete('edit');
        const newUrl = window.location.pathname + (urlParams.toString() ? '?' + urlParams.toString() : '');
        window.history.replaceState({}, '', newUrl);
        
        // Open modal in edit mode
        openSourceModal(parseInt(editId));
    }
});

// Export default init function for universal-initializer
export default function init() {
    // The initialization is already handled in DOMContentLoaded above
    // This is just for compatibility with universal-initializer
    return Promise.resolve();
}