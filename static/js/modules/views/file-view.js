/**
 * File View Renderer
 * Extracted from the legacy file-management-system.js
 */

import { escapeHtml, formatFileSize } from '../core/utils.js';
import { translations } from '../core/config.js';
import { renderFilePaginationControls, updateNavItemCount, initializeFilePaginationControls } from '../rendering/pagination.js';
import { navigationState, fileNavigationState } from '../core/state.js';
import { getFileViewMode } from '../ui/view-mode.js';

/**
 * Render a single file card (for list view)
 */
function renderFileCard(file, fileNumber, filesList, index) {
    const fileSize = formatFileSize(file.size || 0);
    const fileType = file.type || file.file_type || '';
    const fileDate = file.file_date || file.date || file.created_at || '';
    const fileSource = file.source || file.source_name || '';
    const fileSide = file.side || file.side_name || '';
    const safeName = escapeHtml(file.name || `File ${fileNumber}`);
    
    return `
        <div class="file-card fmas-file-record fmas-file-record-list" data-file-id="${file.id}" data-file-name="${safeName}" data-file-index="${index}" onclick="showFileDetails?.(${file.id}, '${safeName}', ${JSON.stringify(filesList).replace(/"/g, '&quot;')}, ${index})">
            <div class="file-card-number">${fileNumber}</div>
            <div class="file-card-icon"><i class="bi bi-file-earmark" aria-hidden="true"></i></div>
            <div class="file-card-body">
                <div class="file-card-name">${safeName}</div>
                <div class="file-card-meta">
                    <span><i class="bi bi-diagram-3"></i> ${escapeHtml(fileSide || '—')}</span>
                    <span><i class="bi bi-building"></i> ${escapeHtml(fileSource || '—')}</span>
                    <span><i class="bi bi-hdd"></i> ${fileSize}</span>
                    <span><i class="bi bi-calendar"></i> ${escapeHtml(fileDate || '—')}</span>
                    <span><i class="bi bi-tag"></i> ${escapeHtml(fileType || '—')}</span>
                </div>
                <div class="file-card-actions">
                    <button class="action-btn" onclick="showFileDetails?.(${file.id}, '${safeName}', ${JSON.stringify(filesList).replace(/"/g, '&quot;')}, ${index}); event.stopPropagation();" title="${translations.viewDetails || 'View Details'}" aria-label="${translations.viewDetailsFor || 'View Details for'} ${safeName}">
                        <i class="bi bi-eye" aria-hidden="true"></i>
                        <span>${translations.viewDetails || 'View Details'}</span>
                    </button>
                    <a class="action-btn" href="/file/${file.id}" target="_blank" rel="noopener" onclick="event.stopPropagation();" title="${translations.openFullView || 'Open Full View'}" aria-label="${translations.openFullViewFor || 'Open Full View for'} ${safeName}">
                        <i class="bi bi-box-arrow-up-right" aria-hidden="true"></i>
                        <span>${translations.fullView || 'Full View'}</span>
                    </a>
                    <button class="action-btn export-btn" onclick="exportFile?.(${file.id}); event.stopPropagation();" title="${translations.exportFile || 'Export File'}" aria-label="${translations.export || 'Export'}: ${safeName}">
                        <i class="bi bi-download" aria-hidden="true"></i>
                        <span class="sr-only">${translations.export || 'Export'}</span>
                    </button>
                </div>
            </div>
            <div class="file-card-select">
                <input type="checkbox" class="file-checkbox" value="${file.id}" aria-label="${translations.selectFile || 'Select file'}: ${safeName}">
            </div>
        </div>
    `;
}

/**
 * Render a file grid item (for grid view)
 */
function renderFileGridItem(file, fileNumber, filesList, index) {
    const fileSize = formatFileSize(file.size || 0);
    const fileType = file.type || file.file_type || '';
    const fileDate = file.file_date || file.date || file.created_at || '';
    const fileSource = file.source || file.source_name || '';
    const fileSide = file.side || file.side_name || '';
    const safeName = escapeHtml(file.name || `File ${fileNumber}`);
    
    return `
        <div class="file-grid-item fmas-file-record fmas-file-record-grid" data-file-id="${file.id}" data-file-name="${safeName}" data-file-index="${index}" onclick="showFileDetails?.(${file.id}, '${safeName}', ${JSON.stringify(filesList).replace(/"/g, '&quot;')}, ${index})">
            <div class="file-card-number">${fileNumber}</div>
            <div class="file-grid-icon-wrap">
                <div class="file-grid-icon">
                    <i class="bi bi-file-earmark" aria-hidden="true"></i>
                </div>
            </div>
            <div class="file-grid-body">
                <div class="file-grid-name" title="${safeName}">${safeName}</div>
                <div class="file-grid-meta">
                    <div><i class="bi bi-tag"></i> ${escapeHtml(fileType || '—')}</div>
                    <div><i class="bi bi-hdd"></i> ${fileSize}</div>
                    <div><i class="bi bi-calendar"></i> ${escapeHtml(fileDate || '—')}</div>
                </div>
                <div class="file-grid-actions">
                    <button class="action-btn action-btn-sm" onclick="showFileDetails?.(${file.id}, '${safeName}', ${JSON.stringify(filesList).replace(/"/g, '&quot;')}, ${index}); event.stopPropagation();" title="${translations.viewDetails || 'View Details'}" aria-label="${translations.viewDetailsFor || 'View Details for'} ${safeName}">
                        <i class="bi bi-eye" aria-hidden="true"></i>
                    </button>
                    <a class="action-btn action-btn-sm" href="/file/${file.id}" target="_blank" rel="noopener" onclick="event.stopPropagation();" title="${translations.openFullView || 'Open Full View'}" aria-label="${translations.openFullViewFor || 'Open Full View for'} ${safeName}">
                        <i class="bi bi-box-arrow-up-right" aria-hidden="true"></i>
                    </a>
                    <button class="action-btn action-btn-sm export-btn" onclick="exportFile?.(${file.id}); event.stopPropagation();" title="${translations.exportFile || 'Export File'}" aria-label="${translations.export || 'Export'}: ${safeName}">
                        <i class="bi bi-download" aria-hidden="true"></i>
                    </button>
                </div>
                <div class="file-grid-select">
                    <input type="checkbox" class="file-checkbox" value="${file.id}" aria-label="${translations.selectFile || 'Select file'}: ${safeName}" onclick="event.stopPropagation();">
                </div>
            </div>
        </div>
    `;
}

export function renderFilesView(files, section, itemName, pagination) {
    const contentView = document.getElementById('unifiedContentView');
    if (!contentView) return;

    let html = '';
    const sectionLabel = section || 'Section';
    html += '<div class="section fmas-section-spaced">';
    html += '<div class="section-header">';
    html += `<div class="section-label"><i class="bi bi-folder"></i> ${escapeHtml(sectionLabel)}: ${escapeHtml(itemName || 'Item')}</div>`;
    html += '</div>';
    html += '</div>';

    if (pagination) {
        navigationState.filePagination = {
            currentPage: pagination.page,
            perPage: pagination.per_page,
            total: pagination.total,
            totalPages: pagination.total_pages,
            totalSize: pagination.total_size,
            has_prev: pagination.has_prev,
            has_next: pagination.has_next
        };
        const startItem = (pagination.page - 1) * pagination.per_page + 1;
        const endItem = Math.min(pagination.page * pagination.per_page, pagination.total);
        updateNavItemCount(startItem, endItem, pagination.total);
    }

    if (files && files.length > 0) {
        html += '<div class="section">';
        html += '<div class="section-header">';
        html += `<div class="section-label">${translations.files || 'Files'}</div>`;
        html += '<div class="file-section-toolbar">';
        html += '<div class="file-search-control">';
        html += `<input type="text" id="fileSearchInput" class="form-control file-search-input" placeholder="${translations.searchFiles || 'Search files...'}" oninput="filterDisplayedFiles?.(this.value)" title="${translations.searchDisplayedFiles || 'Search displayed files'}" aria-label="${translations.searchDisplayedFiles || 'Search displayed files'}">`;
        html += '<i class="bi bi-search file-search-icon"></i>';
        html += '</div>';
        // Per Page control for files
        const currentPerPage = pagination ? pagination.per_page : (navigationState.filePagination?.perPage || 50);
        html += '<div class="per-page-control">';
        html += `<label for="perPageFiles" class="per-page-label">${translations.perPage || 'Per Page:'}</label>`;
        html += `<select id="perPageFiles" class="form-select form-select-sm per-page-select" onchange="handleFilePerPageChange()" title="${translations.itemsPerPage || 'Items Per Page'}" aria-label="${translations.itemsPerPage || 'Items Per Page'}">`;
        html += `<option value="10" ${currentPerPage === 10 ? 'selected' : ''}>10</option>`;
        html += `<option value="25" ${currentPerPage === 25 ? 'selected' : ''}>25</option>`;
        html += `<option value="50" ${currentPerPage === 50 ? 'selected' : ''}>50</option>`;
        html += `<option value="100" ${currentPerPage === 100 ? 'selected' : ''}>100</option>`;
        html += `<option value="200" ${currentPerPage === 200 ? 'selected' : ''}>200</option>`;
        html += '</select>';
        html += '</div>';
        // View mode toggle for files
        const currentFileViewMode = getFileViewMode();
        html += '<div class="file-view-toggle">';
        html += `<button class="view-toggle-btn ${currentFileViewMode === 'list' ? 'active' : ''}" data-view="list" onclick="setFileViewMode('list')" title="${translations.listView || 'List View'}" aria-label="${translations.switchToListView || 'Switch to List View'}">`;
        html += '<i class="bi bi-list-ul" aria-hidden="true"></i>';
        html += '</button>';
        html += `<button class="view-toggle-btn ${currentFileViewMode === 'grid' ? 'active' : ''}" data-view="grid" onclick="setFileViewMode('grid')" title="${translations.gridView || 'Grid View'}" aria-label="${translations.switchToGridView || 'Switch to Grid View'}">`;
        html += '<i class="bi bi-grid-3x3" aria-hidden="true"></i>';
        html += '</button>';
        html += '</div>';
        html += `<button class="action-btn action-btn-secondary" onclick="selectAllFiles?.()" title="${translations.selectAllFiles || 'Select All Files'}" aria-label="${translations.selectAllFiles || 'Select All Files'}">${translations.selectAll || 'Select All'}</button>`;
        html += `<button class="action-btn action-btn-secondary" onclick="deselectAllFiles?.()" title="${translations.deselectAllFiles || 'Deselect All Files'}" aria-label="${translations.deselectAllFiles || 'Deselect All Files'}">${translations.deselectAll || 'Deselect All'}</button>`;
        html += `<button class="action-btn action-btn-success export-btn" onclick="exportSelectedFiles?.()" title="${translations.exportSelectedFiles || 'Export Selected Files'}" aria-label="${translations.exportSelected || 'Export Selected'}">${translations.exportSelected || 'Export Selected'}</button>`;
        html += '</div>';
        html += '</div>';

        const filesList = files.map(file => ({ id: file.id, name: file.name }));
        // Calculate starting number for pagination
        const startNumber = pagination ? (pagination.page - 1) * pagination.per_page + 1 : 1;
        
        // Render files based on view mode
        if (currentFileViewMode === 'grid') {
            // Grid view
            html += '<div class="files-grid-view">';
            files.forEach((file, index) => {
                const fileNumber = startNumber + index;
                html += renderFileGridItem(file, fileNumber, filesList, index);
            });
            html += '</div>';
        } else {
            // List view (default)
            files.forEach((file, index) => {
                const fileNumber = startNumber + index;
                html += renderFileCard(file, fileNumber, filesList, index);
            });
        }

        fileNavigationState.currentFiles = filesList;
        html += renderFilePaginationControls();
        html += '</div>'; // section
    } else {
        html += `<div class="section"><div class="empty-state">${translations.noFilesFound || 'No files found'}</div></div>`;
    }

    contentView.innerHTML = html;
    
    // Initialize pagination controls after DOM is ready
    requestAnimationFrame(() => {
        if (files && files.length > 0 && pagination) {
            // Always initialize pagination if we have pagination data, even if only one page
            // This ensures the pagination info is displayed
            initializeFilePaginationControls();
        }
    });
}