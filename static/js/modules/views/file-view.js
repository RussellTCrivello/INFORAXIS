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
        <div class="file-card" data-file-id="${file.id}" data-file-name="${safeName}" data-file-index="${index}" style="border: 1px solid #e2e8f0; border-radius: 0.5rem; padding: 1rem; margin-bottom: 0.75rem; display: flex; gap: 1rem; align-items: flex-start; cursor: pointer; position: relative;" onclick="showFileDetails?.(${file.id}, '${safeName}', ${JSON.stringify(filesList).replace(/"/g, '&quot;')}, ${index})">
            <div class="file-card-number" style="position: absolute; top: 0.5rem; left: 0.5rem; background: #3b82f6; color: white; width: 28px; height: 28px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 0.75rem; font-weight: 600; z-index: 10; box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);">${fileNumber}</div>
            <div class="file-card-icon"><i class="bi bi-file-earmark" aria-hidden="true"></i></div>
            <div class="file-card-body" style="flex: 1;">
                <div class="file-card-name" style="font-weight: 600; margin-bottom: 0.25rem;">${safeName}</div>
                <div class="file-card-meta" style="color: #64748b; font-size: 0.875rem; display: flex; gap: 1rem; flex-wrap: wrap;">
                    <span><i class="bi bi-diagram-3"></i> ${escapeHtml(fileSide || '—')}</span>
                    <span><i class="bi bi-building"></i> ${escapeHtml(fileSource || '—')}</span>
                    <span><i class="bi bi-hdd"></i> ${fileSize}</span>
                    <span><i class="bi bi-calendar"></i> ${escapeHtml(fileDate || '—')}</span>
                    <span><i class="bi bi-tag"></i> ${escapeHtml(fileType || '—')}</span>
                </div>
                <div class="file-card-actions" style="margin-top: 0.5rem; display: flex; gap: 0.5rem; flex-wrap: wrap;">
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
            <div class="file-card-select" style="display: flex; align-items: center;">
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
        <div class="file-grid-item" data-file-id="${file.id}" data-file-name="${safeName}" data-file-index="${index}" style="border: 1px solid #e2e8f0; border-radius: 0.5rem; padding: 1rem; cursor: pointer; position: relative; background: white; transition: transform 0.2s, box-shadow 0.2s;" onmouseover="this.style.transform='translateY(-2px)'; this.style.boxShadow='0 4px 8px rgba(0,0,0,0.1)'" onmouseout="this.style.transform=''; this.style.boxShadow=''" onclick="showFileDetails?.(${file.id}, '${safeName}', ${JSON.stringify(filesList).replace(/"/g, '&quot;')}, ${index})">
            <div class="file-card-number" style="position: absolute; top: 0.5rem; right: 0.5rem; background: #3b82f6; color: white; width: 28px; height: 28px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 0.75rem; font-weight: 600; z-index: 10; box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);">${fileNumber}</div>
            <div style="text-align: center; margin-bottom: 0.75rem;">
                <div class="file-grid-icon" style="font-size: 3rem; color: #3b82f6; margin-bottom: 0.5rem;">
                    <i class="bi bi-file-earmark" aria-hidden="true"></i>
                </div>
            </div>
            <div class="file-grid-body">
                <div class="file-grid-name" style="font-weight: 600; margin-bottom: 0.5rem; text-align: center; font-size: 0.875rem; line-height: 1.4; min-height: 2.8em; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;" title="${safeName}">${safeName}</div>
                <div class="file-grid-meta" style="color: #64748b; font-size: 0.75rem; display: flex; flex-direction: column; gap: 0.25rem;">
                    <div><i class="bi bi-tag"></i> ${escapeHtml(fileType || '—')}</div>
                    <div><i class="bi bi-hdd"></i> ${fileSize}</div>
                    <div><i class="bi bi-calendar"></i> ${escapeHtml(fileDate || '—')}</div>
                </div>
                <div class="file-grid-actions" style="margin-top: 0.75rem; display: flex; gap: 0.25rem; justify-content: center; flex-wrap: wrap;">
                    <button class="action-btn" style="font-size: 0.75rem; padding: 0.25rem 0.5rem;" onclick="showFileDetails?.(${file.id}, '${safeName}', ${JSON.stringify(filesList).replace(/"/g, '&quot;')}, ${index}); event.stopPropagation();" title="${translations.viewDetails || 'View Details'}" aria-label="${translations.viewDetailsFor || 'View Details for'} ${safeName}">
                        <i class="bi bi-eye" aria-hidden="true"></i>
                    </button>
                    <a class="action-btn" style="font-size: 0.75rem; padding: 0.25rem 0.5rem;" href="/file/${file.id}" target="_blank" rel="noopener" onclick="event.stopPropagation();" title="${translations.openFullView || 'Open Full View'}" aria-label="${translations.openFullViewFor || 'Open Full View for'} ${safeName}">
                        <i class="bi bi-box-arrow-up-right" aria-hidden="true"></i>
                    </a>
                    <button class="action-btn export-btn" style="font-size: 0.75rem; padding: 0.25rem 0.5rem;" onclick="exportFile?.(${file.id}); event.stopPropagation();" title="${translations.exportFile || 'Export File'}" aria-label="${translations.export || 'Export'}: ${safeName}">
                        <i class="bi bi-download" aria-hidden="true"></i>
                    </button>
                </div>
                <div class="file-grid-select" style="margin-top: 0.5rem; text-align: center;">
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
    html += '<div class="section" style="margin-bottom: 1.5rem;">';
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
        html += '<div style="display: flex; gap: 0.5rem; align-items: center; flex-wrap: wrap;">';
        html += '<div style="position: relative; flex: 1; min-width: 200px; max-width: 300px;">';
        html += `<input type="text" id="fileSearchInput" placeholder="${translations.searchFiles || 'Search files...'}" oninput="filterDisplayedFiles?.(this.value)" style="width: 100%; padding: 0.5rem 2.5rem 0.5rem 0.75rem; border: 1px solid #e2e8f0; border-radius: 0.375rem; font-size: 0.875rem;" title="${translations.searchDisplayedFiles || 'Search displayed files'}" aria-label="${translations.searchDisplayedFiles || 'Search displayed files'}">`;
        html += '<i class="bi bi-search" style="position: absolute; right: 0.75rem; top: 50%; transform: translateY(-50%); color: #94a3b8; pointer-events: none;"></i>';
        html += '</div>';
        // Per Page control for files
        const currentPerPage = pagination ? pagination.per_page : (navigationState.filePagination?.perPage || 50);
        html += '<div class="per-page-control" style="display: flex; align-items: center; gap: 0.5rem;">';
        html += `<label for="perPageFiles" style="font-size: 0.875rem; color: var(--text-light); white-space: nowrap;">${translations.perPage || 'Per Page:'}</label>`;
        html += `<select id="perPageFiles" class="form-select form-select-sm" style="min-width: 80px; font-size: 0.875rem;" onchange="handleFilePerPageChange()" title="${translations.itemsPerPage || 'Items Per Page'}" aria-label="${translations.itemsPerPage || 'Items Per Page'}">`;
        html += `<option value="10" ${currentPerPage === 10 ? 'selected' : ''}>10</option>`;
        html += `<option value="25" ${currentPerPage === 25 ? 'selected' : ''}>25</option>`;
        html += `<option value="50" ${currentPerPage === 50 ? 'selected' : ''}>50</option>`;
        html += `<option value="100" ${currentPerPage === 100 ? 'selected' : ''}>100</option>`;
        html += `<option value="200" ${currentPerPage === 200 ? 'selected' : ''}>200</option>`;
        html += '</select>';
        html += '</div>';
        // View mode toggle for files
        const currentFileViewMode = getFileViewMode();
        html += '<div class="file-view-toggle" style="display: flex; align-items: center; gap: 0.25rem; border: 1px solid #e2e8f0; border-radius: 0.375rem; padding: 0.125rem; background: #f8fafc;">';
        html += `<button class="view-toggle-btn ${currentFileViewMode === 'list' ? 'active' : ''}" data-view="list" onclick="setFileViewMode('list')" style="padding: 0.375rem 0.75rem; border: none; background: ${currentFileViewMode === 'list' ? '#3b82f6' : 'transparent'}; color: ${currentFileViewMode === 'list' ? 'white' : '#64748b'}; border-radius: 0.25rem; cursor: pointer; font-size: 0.875rem; transition: all 0.2s;" title="${translations.listView || 'List View'}" aria-label="${translations.switchToListView || 'Switch to List View'}">`;
        html += '<i class="bi bi-list-ul" aria-hidden="true"></i>';
        html += '</button>';
        html += `<button class="view-toggle-btn ${currentFileViewMode === 'grid' ? 'active' : ''}" data-view="grid" onclick="setFileViewMode('grid')" style="padding: 0.375rem 0.75rem; border: none; background: ${currentFileViewMode === 'grid' ? '#3b82f6' : 'transparent'}; color: ${currentFileViewMode === 'grid' ? 'white' : '#64748b'}; border-radius: 0.25rem; cursor: pointer; font-size: 0.875rem; transition: all 0.2s;" title="${translations.gridView || 'Grid View'}" aria-label="${translations.switchToGridView || 'Switch to Grid View'}">`;
        html += '<i class="bi bi-grid-3x3" aria-hidden="true"></i>';
        html += '</button>';
        html += '</div>';
        html += `<button class="action-btn" onclick="selectAllFiles?.()" style="background: #f1f5f9; color: #64748b; border: 1px solid #e2e8f0;" title="${translations.selectAllFiles || 'Select All Files'}" aria-label="${translations.selectAllFiles || 'Select All Files'}">${translations.selectAll || 'Select All'}</button>`;
        html += `<button class="action-btn" onclick="deselectAllFiles?.()" style="background: #f1f5f9; color: #64748b; border: 1px solid #e2e8f0;" title="${translations.deselectAllFiles || 'Deselect All Files'}" aria-label="${translations.deselectAllFiles || 'Deselect All Files'}">${translations.deselectAll || 'Deselect All'}</button>`;
        html += `<button class="action-btn export-btn" onclick="exportSelectedFiles?.()" style="background: #10b981;" title="${translations.exportSelectedFiles || 'Export Selected Files'}" aria-label="${translations.exportSelected || 'Export Selected'}">${translations.exportSelected || 'Export Selected'}</button>`;
        html += '</div>';
        html += '</div>';

        const filesList = files.map(file => ({ id: file.id, name: file.name }));
        // Calculate starting number for pagination
        const startNumber = pagination ? (pagination.page - 1) * pagination.per_page + 1 : 1;
        
        // Render files based on view mode
        if (currentFileViewMode === 'grid') {
            // Grid view
            html += '<div class="files-grid-view" style="display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 1rem; margin-top: 1rem;">';
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