/**
 * Source/Side Categories and Keywords View
 * Shows categories and keywords for a source or side, allowing navigation to files
 */

import { navigationState } from '../core/state.js';
import { sectionLabels, translations } from '../core/config.js';
import { endpoints } from '../api/endpoints.js';
import { apiGet } from '../api/api-client.js';
import { escapeHtml } from '../core/utils.js';
import { loadItemFilesWithFilters } from './item-view.js';

/**
 * Load and display categories and keywords for a source or side
 */
export async function loadSourceCategoriesKeywordsView(section, itemId, itemName = null, page = 1) {
    const contentView = document.getElementById('unifiedContentView');
    if (!contentView) return;
    
    contentView.innerHTML = `<div class="content-loading"><i class="bi bi-arrow-repeat"></i><div>${translations.loading || 'Loading...'}</div></div>`;

    try {
        // Determine which endpoint to use based on section
        const endpoint = section === 'sources' 
            ? endpoints.sourceCategoriesKeywords(itemId, { page })
            : endpoints.sideCategoriesKeywords(itemId, { page });
        
        console.log('Loading categories/keywords from:', endpoint);
        
        const data = await apiGet(endpoint);
        console.log('Categories/Keywords data received:', data);
        
        if (!data.success) {
            throw new Error(data.error || 'Failed to load categories and keywords');
        }

        // Store context for navigation
        navigationState.currentSourceId = section === 'sources' ? itemId : null;
        navigationState.currentSideId = section === 'sides' ? itemId : null;
        navigationState.currentSourceSection = section;
        navigationState.currentSourceItemId = itemId;
        navigationState.currentSourceItemName = itemName;

        // Render the view
        renderSourceCategoriesKeywordsView(
            data.categories || [],
            data.keywords || [],
            section,
            itemId,
            itemName || sectionLabels[section] || 'Item',
            data.pagination || {}
        );
    } catch (error) {
        console.error('Error loading categories/keywords:', error);
        contentView.innerHTML = `<div class="empty-state">${translations.errorLoadingItems || 'Error loading items'}: ${error.message}</div>`;
    }
}

/**
 * Render categories and keywords view
 */
function renderSourceCategoriesKeywordsView(categories, keywords, section, itemId, itemName, pagination) {
    const contentView = document.getElementById('unifiedContentView');
    if (!contentView) return;

    const sectionLabel = sectionLabels[section] || section;
    const sectionType = section === 'sources' ? 'source' : 'side';
    const sectionIdParam = section === 'sources' ? 'source_id' : 'side_id';

    let html = `
        <div class="source-categories-keywords-view">
            <div class="source-categories-header">
                <h2 class="source-categories-title">
                    <i class="bi bi-${section === 'sources' ? 'people' : 'diagram-3'}"></i>
                    ${escapeHtml(itemName)}
                </h2>
                <p class="source-categories-subtitle">
                    ${translations.categories || 'Categories'} & ${translations.keywords || 'Keywords'}
                </p>
            </div>

            <div class="categories-section source-linkage-section">
                <h3 class="source-linkage-title">
                    <i class="bi bi-folder-fill source-linkage-icon"></i>
                    ${translations.categories || 'Categories'}
                    <span class="badge bg-secondary source-linkage-count">${categories.length}</span>
                </h3>
    `;

    if (categories.length === 0) {
        html += `
            <div class="empty-state source-linkage-empty">
                <i class="bi bi-folder-x source-linkage-empty-icon"></i>
                <p>${translations.noCategoriesAssigned || 'No categories found for this ' + sectionType}</p>
            </div>
        `;
    } else {
        html += '<div class="categories-grid source-linkage-grid">';
        
        categories.forEach(category => {
            const categoryName = escapeHtml(category.name || 'Unnamed Category');
            const fileCount = category.file_count || 0;
            
            html += `
                <div class="category-card source-linkage-card"
                     data-section="category"
                     data-item-id="${category.id}"
                     data-item-name="${categoryName}"
                     data-${sectionIdParam}="${itemId}">
                    <div class="source-linkage-card-header">
                        <i class="bi bi-folder-fill source-linkage-card-icon"></i>
                        <h4 class="source-linkage-card-title">${categoryName}</h4>
                    </div>
                    <div class="source-linkage-card-meta">
                        <i class="bi bi-file-earmark"></i>
                        <span>${fileCount} ${translations.files || 'files'}</span>
                    </div>
                </div>
            `;
        });
        
        html += '</div>';
    }

    html += `
            </div>

            <div class="keywords-section source-linkage-section">
                <h3 class="source-linkage-title">
                    <i class="bi bi-tag-fill source-linkage-icon"></i>
                    ${translations.keywords || 'Keywords'}
                    <span class="badge bg-secondary source-linkage-count">${keywords.length}</span>
                </h3>
    `;

    if (keywords.length === 0) {
        html += `
            <div class="empty-state source-linkage-empty">
                <i class="bi bi-tag source-linkage-empty-icon"></i>
                <p>${translations.noKeywordsFound || 'No keywords found for this ' + sectionType}</p>
            </div>
        `;
    } else {
        html += '<div class="keywords-grid source-linkage-grid">';
        
        keywords.forEach(keyword => {
            const keywordName = escapeHtml(keyword.name || 'Unnamed Keyword');
            const fileCount = keyword.file_count || 0;
            
            html += `
                <div class="keyword-card source-linkage-card"
                     data-section="keywords"
                     data-item-id="${keyword.id}"
                     data-item-name="${keywordName}"
                     data-${sectionIdParam}="${itemId}">
                    <div class="source-linkage-card-header">
                        <i class="bi bi-tag-fill source-linkage-card-icon"></i>
                        <h4 class="source-linkage-card-title">${keywordName}</h4>
                    </div>
                    <div class="source-linkage-card-meta">
                        <i class="bi bi-file-earmark"></i>
                        <span>${fileCount} ${translations.files || 'files'}</span>
                    </div>
                </div>
            `;
        });
        
        html += '</div>';
    }

    html += `
            </div>
        </div>
    `;

    contentView.innerHTML = html;

    // Add click handlers for categories and keywords
    setupCategoryKeywordClickHandlers();
}

/**
 * Setup click handlers for category and keyword cards
 */
function setupCategoryKeywordClickHandlers() {
    const cards = document.querySelectorAll('.category-card, .keyword-card');
    
    cards.forEach(card => {
        card.addEventListener('click', function(e) {
            e.preventDefault();
            e.stopPropagation();
            
            const section = this.getAttribute('data-section');
            const itemId = parseInt(this.getAttribute('data-item-id'));
            const itemName = this.getAttribute('data-item-name');
            const sourceId = this.getAttribute('data-source_id');
            const sideId = this.getAttribute('data-side_id');
            
            console.log('Category/Keyword clicked:', { section, itemId, itemName, sourceId, sideId });
            
            // Use loadItemFilesWithFilters with filters
            const sourceFilter = sourceId ? { source_id: parseInt(sourceId) } : null;
            const sideFilter = sideId ? { side_id: parseInt(sideId) } : null;
            
            loadItemFilesWithFilters(section, itemId, itemName, sourceFilter, sideFilter, 1);
        });
    });
}

