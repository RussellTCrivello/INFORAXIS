/**
 * Sides List Page JavaScript
 * Extracted from Side/sides_list.html
 */

// Load translations from JSON script tag
let translations = {};

document.addEventListener('DOMContentLoaded', function() {
    // Load translations from JSON script tag
    const pageDataEl = document.getElementById('sides-list-page-data');
    if (pageDataEl) {
        try {
            const data = JSON.parse(pageDataEl.textContent);
            translations = data.translations || {};
            // Also make available on window for backward compatibility
            window.translations = window.translations || {};
            Object.assign(window.translations, translations);
        } catch (e) {
            console.error('Error parsing sides list page data:', e);
        }
    }
    
    console.log('Sides list page loaded');
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
let allSides = [];
let filteredSides = [];
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
    return document.getElementById('sidesCardContainer');
}

function sideFromElement(item) {
    const dataset = item.dataset || {};
    const displayName = dataset.displayName || item.querySelector('.id-card-name')?.textContent?.trim() || dataset.name || '';
    return {
        id: String(dataset.id || '').trim(),
        name: String(dataset.name || displayName).toLowerCase(),
        nameDisplay: displayName,
        importance: parseFloat(dataset.importance) || 0,
        docCount: parseInt(dataset.docCount, 10) || 0,
        sourceCount: parseInt(dataset.sourceCount, 10) || 0,
        createdDate: dataset.createdDate || '',
        element: item
    };
}

function normalizeSideRecord(side) {
    const displayName = side.nameDisplay || side.name || '';
    return {
        id: String(side.id || '').trim(),
        name: String(displayName).toLowerCase(),
        nameDisplay: displayName,
        importance: Number.isFinite(Number(side.importance)) ? Number(side.importance) : 0.5,
        docCount: Number.isFinite(Number(side.docCount)) ? Number(side.docCount) : 0,
        sourceCount: Number.isFinite(Number(side.sourceCount)) ? Number(side.sourceCount) : 0,
        createdDate: side.createdDate || '',
        element: side.element || null
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

function sideActions(side, compact = false) {
    const id = escapeAttr(side.id);
    const nameJson = escapeAttr(JSON.stringify(side.nameDisplay || ''));
    const viewLabel = translations.viewDetails || translations.view || 'View';
    const label = compact ? '' : ` <span class="d-none d-xl-inline">${escapeHtml(viewLabel)}</span>`;
    return `
        <div class="btn-group btn-group-sm ia-action-group" role="group" aria-label="${escapeAttr(translations.sideActions || 'Side actions')}">
            <button class="btn btn-outline-primary" onclick="viewSide(${id})" title="${escapeAttr(viewLabel)}"><i class="bi bi-eye"></i>${label}</button>
            <button class="btn btn-outline-success" onclick="editSide(${id})" title="${escapeAttr(translations.editSide || 'Edit side')}"><i class="bi bi-pencil"></i></button>
            <button class="btn btn-outline-info" onclick="duplicateSide(${id})" title="${escapeAttr(translations.duplicateSide || 'Duplicate side')}"><i class="bi bi-files"></i></button>
            <button class="btn btn-outline-secondary" onclick="exportSide(${id})" title="${escapeAttr(translations.exportData || 'Export data')}"><i class="bi bi-download"></i></button>
            <button class="btn btn-outline-primary" onclick="viewSideCategoriesKeywords(${id})" title="${escapeAttr(translations.viewCategoriesKeywords || 'View categories and keywords')}"><i class="bi bi-tags"></i></button>
            <button class="btn btn-outline-danger" onclick='deleteSide(${id}, ${nameJson})' title="${escapeAttr(translations.deleteSide || 'Delete side')}"><i class="bi bi-trash"></i></button>
        </div>`;
}

function createSideCard(side) {
    const card = document.createElement('div');
    card.className = 'col-md-6 col-lg-4 col-xl-3 side-card-item';
    card.dataset.name = side.name;
    card.dataset.displayName = side.nameDisplay;
    card.dataset.importance = side.importance;
    card.dataset.docCount = side.docCount;
    card.dataset.sourceCount = side.sourceCount;
    card.dataset.createdDate = side.createdDate || '';
    card.dataset.id = side.id;
    card.innerHTML = `
        <div class="id-card ia-record-card">
            <div class="id-card-header">
                <div class="id-card-icon"><i class="bi bi-diagram-3"></i></div>
                <div class="id-card-id"><span class="badge bg-secondary">#${escapeHtml(side.id)}</span></div>
            </div>
            <div class="id-card-body">
                <h3 class="id-card-name">${escapeHtml(side.nameDisplay)}</h3>
                <div class="id-card-info">
                    <div class="id-card-field"><i class="bi bi-star text-muted"></i><span class="id-card-label">${escapeHtml(translations.importance || 'Importance')}:</span><div class="id-card-stars">${renderStars(side.importance)}<span class="ms-2 text-muted">(${formatImportance(side.importance)})</span></div></div>
                    <div class="id-card-field"><i class="bi bi-building text-muted"></i><span class="id-card-label">${escapeHtml(translations.sources || 'Sources')}:</span><span class="badge bg-info">${side.sourceCount}</span></div>
                    <div class="id-card-field"><i class="bi bi-file-earmark text-muted"></i><span class="id-card-label">${escapeHtml(translations.documents || 'Documents')}:</span><span class="badge bg-primary">${side.docCount}</span></div>
                    <div class="id-card-field"><i class="bi bi-calendar text-muted"></i><span class="id-card-label">${escapeHtml(translations.created || 'Created')}:</span><span class="id-card-value">${escapeHtml(side.createdDate || '—')}</span></div>
                </div>
            </div>
            <div class="id-card-footer">
                <div class="d-flex align-items-center mb-2">
                    <input type="checkbox" class="form-check-input side-checkbox me-2" value="${escapeAttr(side.id)}" onchange="updateBulkButtons()" aria-label="Select side: ${escapeAttr(side.nameDisplay)}">
                    <small class="text-muted">${escapeHtml(translations.select || 'Select')}</small>
                </div>
                ${sideActions(side, true)}
            </div>
        </div>`;
    return card;
}

function ensureStructuredViews() {
    const grid = getRecordContainer();
    if (!grid || !grid.parentElement) return {};
    let tableView = document.getElementById('sidesTableView');
    let listView = document.getElementById('sidesListView');
    if (!tableView) {
        tableView = document.createElement('div');
        tableView.id = 'sidesTableView';
        tableView.className = 'sides-structured-view d-none';
        grid.parentElement.insertBefore(tableView, grid.nextSibling);
    }
    if (!listView) {
        listView = document.createElement('div');
        listView.id = 'sidesListView';
        listView.className = 'sides-structured-view ia-record-list d-none';
        grid.parentElement.insertBefore(listView, tableView.nextSibling);
    }
    return { grid, tableView, listView };
}

function renderSidesTable(records) {
    const { tableView } = ensureStructuredViews();
    if (!tableView) return;
    tableView.innerHTML = `
        <div class="table-wrapper sides-table-wrapper">
            <table class="table table-hover align-middle sides-table" id="sidesTable" data-ia-table="sides" data-ia-title="Sides" data-ia-sort="true" data-ia-toolbar="true">
                <thead>
                    <tr>
                        <th style="width:44px"><input type="checkbox" onchange="this.closest('table').querySelectorAll('.side-checkbox').forEach(cb => cb.checked = this.checked); updateBulkButtons();"></th>
                        <th>ID</th><th>${escapeHtml(translations.side || 'Side')}</th><th>${escapeHtml(translations.importance || 'Importance')}</th><th>${escapeHtml(translations.sources || 'Sources')}</th><th>${escapeHtml(translations.documents || 'Documents')}</th><th>${escapeHtml(translations.created || 'Created')}</th><th>${escapeHtml(translations.actions || 'Actions')}</th>
                    </tr>
                </thead>
                <tbody>
                    ${records.map(side => `
                        <tr data-side-id="${escapeAttr(side.id)}">
                            <td><input type="checkbox" class="form-check-input side-checkbox" value="${escapeAttr(side.id)}" onchange="updateBulkButtons()"></td>
                            <td><span class="badge bg-secondary">#${escapeHtml(side.id)}</span></td>
                            <td><strong title="${escapeAttr(side.nameDisplay)}">${escapeHtml(side.nameDisplay)}</strong></td>
                            <td data-sort-value="${Number(side.importance) || 0}"><span class="badge bg-primary">${formatImportance(side.importance)}</span></td>
                            <td data-sort-value="${side.sourceCount}"><span class="badge bg-info">${side.sourceCount}</span></td>
                            <td data-sort-value="${side.docCount}"><span class="badge bg-primary">${side.docCount}</span></td>
                            <td>${escapeHtml(side.createdDate || '—')}</td>
                            <td>${sideActions(side, true)}</td>
                        </tr>`).join('')}
                </tbody>
            </table>
        </div>`;
}

function renderSidesList(records) {
    const { listView } = ensureStructuredViews();
    if (!listView) return;
    listView.innerHTML = records.map(side => `
        <div class="ia-record-list-row side-card-item" data-id="${escapeAttr(side.id)}" data-name="${escapeAttr(side.name)}">
            <div class="d-flex flex-wrap justify-content-between align-items-center gap-2">
                <div class="min-w-0">
                    <div class="d-flex align-items-center gap-2">
                        <span class="badge bg-secondary">#${escapeHtml(side.id)}</span>
                        <strong class="ia-truncate" title="${escapeAttr(side.nameDisplay)}">${escapeHtml(side.nameDisplay)}</strong>
                        <span class="badge bg-primary">${formatImportance(side.importance)}</span>
                    </div>
                    <div class="small text-muted mt-1">${side.sourceCount} ${escapeHtml((translations.sources || 'sources').toLowerCase())} · ${side.docCount} ${escapeHtml((translations.documents || 'documents').toLowerCase())} · ${escapeHtml(side.createdDate || (translations.noCreationDate || 'No creation date'))}</div>
                </div>
                ${sideActions(side, true)}
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
        filteredSides.forEach((side, index) => {
            if (!side.element) {
                side.element = createSideCard(side);
                grid.appendChild(side.element);
            }
            side.element.style.display = '';
            side.element.style.order = index;
        });
        allSides.forEach(side => {
            if (!filteredSides.includes(side) && side.element) side.element.style.display = 'none';
        });
    } else {
        allSides.forEach(side => {
            if (side.element) side.element.style.display = 'none';
        });
        if (currentFormat === 'table') renderSidesTable(filteredSides);
        if (currentFormat === 'list') renderSidesList(filteredSides);
    }

    window.InforaxisDataInterface?.refresh(grid.parentElement || document);
}

function upsertSideRecord(side, highlight = true) {
    const normalized = normalizeSideRecord(side);
    const index = allSides.findIndex(item => String(item.id) === String(normalized.id));
    if (index >= 0) {
        normalized.element = allSides[index].element;
        if (normalized.element) {
            const replacement = createSideCard(normalized);
            normalized.element.replaceWith(replacement);
            normalized.element = replacement;
        }
        allSides[index] = normalized;
    } else {
        normalized.element = createSideCard(normalized);
        getRecordContainer()?.appendChild(normalized.element);
        allSides.unshift(normalized);
    }
    applyFilters();
    if (highlight) {
        const selector = currentFormat === 'table'
            ? `#sidesTable tr[data-side-id="${CSS.escape(String(normalized.id))}"]`
            : currentFormat === 'list'
                ? `#sidesListView [data-id="${CSS.escape(String(normalized.id))}"]`
                : normalized.element;
        window.InforaxisDataInterface?.highlightNewRecord(selector);
    }
}

function removeSideRecord(sideId) {
    const index = allSides.findIndex(item => String(item.id) === String(sideId));
    if (index >= 0) {
        const [removed] = allSides.splice(index, 1);
        removed.element?.remove();
    }
    document.querySelectorAll(`[data-side-id="${CSS.escape(String(sideId))}"], .side-card-item[data-id="${CSS.escape(String(sideId))}"]`).forEach(el => el.remove());
    applyFilters();
    updateBulkButtons();
}

// Initialize sides data from DOM
function initializeSidesData() {
    const sideItems = document.querySelectorAll('.side-card-item[data-id]');
    const map = new Map();

    sideItems.forEach(item => {
        const side = sideFromElement(item);
        if (side.id && !map.has(side.id)) {
            map.set(side.id, side);
        }
    });

    allSides = Array.from(map.values());
    filteredSides = [...allSides];

    const formatSelect = document.getElementById('displayFormat');
    const savedFormat = safeLocalStorageRef()?.getItem('inforaxis.sides.displayFormat');
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
    const totalCount = allSides.length;
    const filteredCount = filteredSides.length;
    const visibleCount = filteredSides.length;

    const totalEl = document.getElementById('totalSidesCount');
    const filteredEl = document.getElementById('filteredSidesCount');
    const visibleEl = document.getElementById('visibleSidesCount');
    const pageEl = document.getElementById('currentPageInfo');

    if (totalEl) totalEl.textContent = totalCount.toLocaleString();
    if (filteredEl) filteredEl.textContent = filteredCount.toLocaleString();
    if (visibleEl) visibleEl.textContent = visibleCount.toLocaleString();
    if (pageEl && filteredCount <= allSides.length) pageEl.textContent = `1 / ${Math.max(1, Math.ceil(filteredCount / Math.max(1, itemsPerPage)))}`;
}

// Apply filters and sorting
function applyFilters() {
    const searchInput = document.getElementById('sideSearch');
    const sortBy = document.getElementById('sortBy');

    const searchTerm = (searchInput?.value || '').toLowerCase().trim();
    currentSort = sortBy?.value || 'importance-desc';

    filteredSides = allSides.filter(side => {
        if (!searchTerm) return true;
        return [side.name, side.nameDisplay]
            .join(' ')
            .toLowerCase()
            .includes(searchTerm);
    });

    const [sortField, sortDirection] = currentSort.split('-');
    filteredSides.sort((a, b) => {
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
            case 'source_count':
                aVal = a.sourceCount || 0;
                bVal = b.sourceCount || 0;
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
    safeLocalStorageRef()?.setItem('inforaxis.sides.displayFormat', currentFormat);
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
function getActiveSidesContainer() {
    return currentFormat === 'table'
        ? document.getElementById('sidesTableView')
        : currentFormat === 'list'
            ? document.getElementById('sidesListView')
            : document.getElementById('sidesCardContainer');
}

function getSelectedSideIds() {
    const activeContainer = getActiveSidesContainer();
    const checkboxes = activeContainer ? activeContainer.querySelectorAll('.side-checkbox:checked') : document.querySelectorAll('.side-checkbox:checked');
    return Array.from(new Set(Array.from(checkboxes).map(cb => parseInt(cb.value, 10)).filter(Boolean)));
}

function selectAll() {
    const activeContainer = getActiveSidesContainer();
    const checkboxes = activeContainer ? activeContainer.querySelectorAll('.side-checkbox') : document.querySelectorAll('.side-checkbox');
    checkboxes.forEach(cb => { cb.checked = true; });
    updateBulkButtons();
}

function selectNone() {
    document.querySelectorAll('.side-checkbox').forEach(cb => { cb.checked = false; });
    updateBulkButtons();
}

function updateBulkButtons() {
    const hasSelection = getSelectedSideIds().length > 0;

    const bulkExportBtn = document.getElementById('bulkExportBtn');
    const bulkUpdateBtn = document.getElementById('bulkUpdateBtn');

    if (bulkExportBtn) bulkExportBtn.disabled = !hasSelection;
    if (bulkUpdateBtn) bulkUpdateBtn.disabled = !hasSelection;
}

// Bulk operations
function bulkExport() {
    const selectedIds = getSelectedSideIds();
    
    if (selectedIds.length === 0) {
        showToast('Please select sides to export', 'warning');
        return;
    }
    
    // Export functionality - would need backend endpoint
    showToast(`Exporting ${selectedIds.length} side(s)...`, 'info');
    console.log('Bulk export:', selectedIds);
}

function bulkUpdate() {
    const selectedIds = getSelectedSideIds();
    
    if (selectedIds.length === 0) {
        showToast('Please select sides to update', 'warning');
        return;
    }
    
    // Bulk update functionality - would need backend endpoint
    showToast(`Updating ${selectedIds.length} side(s)...`, 'info');
    console.log('Bulk update:', selectedIds);
}

// Export single side
function exportSide(sideId) {
    // Export functionality - would need backend endpoint
    showToast('Exporting side data...', 'info');
    console.log('Export side:', sideId);
}

// Clear search
function clearSearch() {
    const searchInput = document.getElementById('sideSearch');
    if (searchInput) {
        searchInput.value = '';
        applyFilters();
    }
}

// View side categories and keywords
function viewSideCategoriesKeywords(sideId) {
    window.location.href = `/sides/${sideId}/categories-keywords`;
}

// Initialize event listeners
function initializeEventListeners() {
    const searchInput = document.getElementById('sideSearch');
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
        if (e.target.classList.contains('side-checkbox')) {
            updateBulkButtons();
        }
    });
}

// Initialize on DOM ready
document.addEventListener('DOMContentLoaded', function() {
    initializeSidesData();
    initializeEventListeners();
    applyFilters();
});

// Make functions globally accessible
window.selectAll = selectAll;
window.selectNone = selectNone;
window.updateBulkButtons = updateBulkButtons;
window.bulkExport = bulkExport;
window.bulkUpdate = bulkUpdate;
window.clearSearch = clearSearch;
window.applyFilters = applyFilters;
window.changeDisplayFormat = changeDisplayFormat;
window.changePageSize = changePageSize;
window.viewSideCategoriesKeywords = viewSideCategoriesKeywords;
window.exportSide = exportSide;

function viewSide(sideId) {
    window.location.href = `/sides/${sideId}`;
}

function editSide(sideId) {
    openSideModal(sideId);
}



function duplicateSide(sideId) {
    if (confirm(translations.createCopyOfSide)) {
        const csrfToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content') || '';
        fetch(`/api/sides/${sideId}/duplicate`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrfToken
            }
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                const original = allSides.find(side => String(side.id) === String(sideId));
                if (original && data.new_side_id) {
                    const duplicated = normalizeSideRecord({
                        ...original,
                        id: data.new_side_id,
                        name: data.new_name || `${original.nameDisplay} (Copy)`,
                        nameDisplay: data.new_name || `${original.nameDisplay} (Copy)`,
                        docCount: 0,
                        sourceCount: 0,
                        element: null
                    });
                    upsertSideRecord(duplicated, true);
                } else {
                    setTimeout(() => {
                        window.location.href = window.location.pathname + '?t=' + Date.now();
                    }, 500);
                }
                showToast(translations.sideDuplicatedSuccessfully || 'Side duplicated successfully!', 'success');
            } else {
                showToast((translations.errorDuplicatingSide || 'Error duplicating side') + ': ' + (data.message || (translations.unknownError || 'Unknown error')), 'error');
            }
        })
        .catch(error => {
            console.error('Error:', error);
            showToast(translations.errorDuplicatingSide || 'Error duplicating side', 'error');
        });
    }
}

function toggleSideStatus(sideId) {
    const csrfToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content') || '';
    fetch(`/api/sides/${sideId}/toggle-status`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': csrfToken
        }
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showToast(translations.sideStatusUpdated || 'Side status updated!', 'success');
            setTimeout(() => {
                window.location.href = window.location.pathname + '?t=' + Date.now();
            }, 500);
        } else {
            showToast((translations.errorUpdatingStatus || 'Error updating status') + ': ' + (data.message || (translations.unknownError || 'Unknown error')), 'error');
        }
    })
    .catch(error => {
        console.error('Error:', error);
        showToast(translations.errorUpdatingSideStatus || 'Error updating side status', 'error');
    });
}

function deleteSide(sideId, sideName = '') {
    const confirmMessage = sideName 
        ? `${translations.areYouSureDeleteSide || 'Are you sure you want to delete the side'} "${sideName}"?\n\n${translations.actionCannotBeUndone || 'This action cannot be undone.'}`
        : translations.deleteSideConfirm;
    
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
            window.MessageFormatter.showNotification('delete', 'processing', { item: sideName || 'Side' });
        }
        
        const csrfToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content') || '';
        fetch(`/api/sides/${sideId}`, {
            method: 'DELETE',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrfToken
            }
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                // Show formatted success notification
                if (window.MessageFormatter) {
                    window.MessageFormatter.showDeleteSuccess(sideName || 'Side', {
                        title: translations.sideDeleted || 'Side Deleted',
                        duration: 4000
                    });
                } else {
                    showToast(translations.sideDeletedSuccessfully || 'Side deleted successfully!', 'success');
                }
                removeSideRecord(sideId);
            } else {
                // Show formatted error notification
                if (window.MessageFormatter) {
                    window.MessageFormatter.showDeleteError(sideName || 'Side', {
                        title: translations.deleteFailed || 'Delete Failed',
                        duration: 6000
                    });
                } else {
                    showToast((translations.errorDeletingSide || 'Error deleting side') + ': ' + (data.error || (translations.unknownError || 'Unknown error')), 'error');
                }
            }
        })
        .catch(error => {
            console.error('Error:', error);
            if (window.MessageFormatter) {
                window.MessageFormatter.showDeleteError(sideName || 'Side', {
                    title: translations.deleteError || 'Delete Error',
                    duration: 6000
                });
            } else {
                showToast(translations.errorDeletingSide || 'Error deleting side', 'error');
            }
        });
    });
    
    modal.show();
}

// Modal functions
function openSideModal(sideId = null) {
    const modal = new bootstrap.Modal(document.getElementById('sideModal'));
    const form = document.getElementById('sideForm');
    const modalTitle = document.getElementById('modalTitle');
    const submitButtonText = document.getElementById('submitButtonText');
    
    // Reset form
    form.reset();
    document.getElementById('sideId').value = '';
    document.getElementById('importanceSlider').value = '0.5';
    document.getElementById('importanceValue').textContent = '0.50';
    
    if (sideId) {
        // Edit mode
        modalTitle.textContent = translations.editSide || 'Edit Side';
        submitButtonText.textContent = translations.updateSide || 'Update Side';
        document.getElementById('modalIcon').className = 'bi bi-pencil me-2';
        document.getElementById('sideId').value = sideId;
        
        // Load side data
        fetch(`/api/sides/${sideId}`)
            .then(response => {
                if (!response.ok) {
                    return response.json().then(err => {
                        throw new Error(err.error || `HTTP error! status: ${response.status}`);
                    });
                }
                return response.json();
            })
            .then(data => {
                if (data.success && data.side) {
                    const side = data.side;
                    document.getElementById('sideName').value = side.name || '';
                    
                    const importance = side.importance || 0.5;
                    document.getElementById('importanceSlider').value = importance;
                    document.getElementById('importanceValue').textContent = parseFloat(importance).toFixed(2);
                } else {
                    showToast((translations.errorLoadingSide || 'Error loading side') + ': ' + (data.error || (translations.unknownError || 'Unknown error')), 'error');
                    modal.hide();
                }
            })
            .catch(error => {
                console.error('Error loading side data:', error);
                showToast((translations.errorLoadingSideData || 'Error loading side data') + ': ' + error.message, 'error');
                modal.hide();
            });
    } else {
        // Add mode
        modalTitle.textContent = translations.addNewSide || 'Add New Side';
        submitButtonText.textContent = translations.createSide || 'Create Side';
        document.getElementById('modalIcon').className = 'bi bi-plus-circle me-2';
    }
    
    modal.show();
}

async function submitSideForm() {
    const form = document.getElementById('sideForm');
    const sideId = document.getElementById('sideId').value;
    const submitButton = document.querySelector('#sideModal .modal-footer .btn-primary');
    const formData = new FormData(form);

    if (!formData.get('name')) {
        form.classList.add('was-validated');
        showToast(translations.pleaseFillInSideName || 'Please fill in the side name', 'warning');
        return;
    }

    const data = {
        name: formData.get('name'),
        importance: parseFloat(formData.get('importance')) || 0.5
    };

    const url = sideId ? `/api/sides/${sideId}` : '/api/sides';
    const method = sideId ? 'PUT' : 'POST';
    const sideName = data.name || 'Side';
    const isEdit = !!sideId;
    const csrfToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content') || '';

    window.InforaxisDataInterface?.setButtonBusy(submitButton, true, {
        label: isEdit ? (translations.updateSide || 'Update Side') : (translations.createSide || 'Create Side')
    });

    try {
        const response = await fetch(url, {
            method: method,
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrfToken
            },
            body: JSON.stringify(data)
        });
        const result = await response.json().catch(() => ({}));
        if (!response.ok || result.success === false) {
            throw new Error(result.error || `HTTP error! status: ${response.status}`);
        }

        if (window.MessageFormatter && typeof window.MessageFormatter.showCreateSuccess === 'function') {
            if (isEdit) {
                window.MessageFormatter.showUpdateSuccess(sideName, { title: 'Side Updated', duration: 4000 });
            } else {
                window.MessageFormatter.showCreateSuccess(sideName, { title: 'Side Created', duration: 4000 });
            }
        } else {
            showToast(
                isEdit ? (translations.sideUpdatedSuccessfully || 'Side updated successfully!') : (translations.sideCreatedSuccessfully || 'Side created successfully!'),
                'success'
            );
        }

        const savedId = String(sideId || result.id || result.side?.id || result.side_id || '');
        if (savedId) {
            const existing = allSides.find(item => String(item.id) === savedId);
            upsertSideRecord({
                id: savedId,
                nameDisplay: sideName,
                importance: data.importance,
                docCount: existing?.docCount || 0,
                sourceCount: existing?.sourceCount || 0,
                createdDate: existing?.createdDate || new Date().toISOString().slice(0, 10),
                element: existing?.element || null
            }, true);
        } else {
            window.location.href = window.location.pathname + '?t=' + Date.now();
        }

        bootstrap.Modal.getInstance(document.getElementById('sideModal'))?.hide();
        form.reset();
    } catch (error) {
        console.error('Error saving side:', error);
        if (window.MessageFormatter && typeof window.MessageFormatter.showCreateError === 'function') {
            if (isEdit) {
                window.MessageFormatter.showUpdateError(sideName, { title: 'Update Error', duration: 6000 });
            } else {
                window.MessageFormatter.showCreateError(sideName, { title: 'Create Error', duration: 6000 });
            }
        } else {
            showToast((translations.errorSavingSide || 'Error saving side') + ': ' + error.message, 'error');
        }
    } finally {
        window.InforaxisDataInterface?.setButtonBusy(submitButton, false);
    }
}

// Make functions globally accessible for onclick handlers
window.viewSide = viewSide;
window.editSide = editSide;
window.duplicateSide = duplicateSide;
window.toggleSideStatus = toggleSideStatus;
window.deleteSide = deleteSide;
window.openSideModal = openSideModal;
window.submitSideForm = submitSideForm;
window.viewSideCategoriesKeywords = viewSideCategoriesKeywords;
window.exportSide = exportSide;

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
        openSideModal(parseInt(editId));
    }
});

// Export default init function for universal-initializer
export default function init() {
    // The initialization is already handled in DOMContentLoaded above
    // This is just for compatibility with universal-initializer
    return Promise.resolve();
}