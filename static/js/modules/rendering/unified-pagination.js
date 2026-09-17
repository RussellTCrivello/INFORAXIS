/**
 * Unified Pagination Module
 * Provides consistent pagination rendering across all pages
 */

/**
 * Render unified pagination controls
 * @param {Object} options - Pagination options
 * @param {number} options.currentPage - Current page number (1-based)
 * @param {number} options.totalPages - Total number of pages
 * @param {number} options.totalItems - Optional total record count for range metadata
 * @param {number} options.pageSize - Optional page size for range metadata
 * @param {string} options.itemLabel - Optional item label used in range metadata
 * @param {number} options.visiblePageCount - Number of numeric page buttons to keep visible
 * @param {string} options.containerId - ID of container element
 * @param {Function} options.onPageChange - Callback function when page changes
 * @param {Object} options.urlParams - URL parameters to preserve
 * @param {boolean} options.showInfo - Whether to show pagination info
 * @param {boolean} options.showJump - Whether to show jump to page input
 * @param {string} options.endpoint - Flask endpoint name (for URL building)
 * @param {string} options.baseUrl - Base URL (alternative to endpoint)
 * @param {Object} options.labels - Optional labels for localization
 */
export function renderUnifiedPagination(options) {
    const {
        currentPage = 1,
        totalPages = 1,
        totalItems = null,
        pageSize = null,
        itemLabel = 'records',
        visiblePageCount = 5,
        containerId = 'paginationContainer',
        onPageChange = null,
        urlParams = {},
        showInfo = true,
        showJump = true,
        endpoint = null,
        baseUrl = null,
        labels = {}
    } = options;

    const container = document.getElementById(containerId);
    if (!container) {
        console.warn(`Pagination container not found: ${containerId}`);
        return;
    }

    // Validate and clamp page numbers
    const totalPagesValid = Math.max(1, Math.ceil(totalPages || 1));
    const pageValid = Math.max(1, Math.min(Math.max(1, currentPage || 1), totalPagesValid));
    
    // Don't show pagination if only one page or no pages
    if (totalPagesValid <= 1) {
        container.innerHTML = '';
        return;
    }

    // Use validated values
    const page = pageValid;
    const totalPagesFinal = totalPagesValid;
    const { startPage, endPage } = getPageWindow(page, totalPagesFinal, visiblePageCount);
    const metadata = buildPaginationMetadata({
        page,
        totalPages: totalPagesFinal,
        totalItems,
        pageSize,
        itemLabel,
        labels
    });

    // Check if container is already a unified-pagination-container
    const isAlreadyUnifiedContainer = container.classList.contains('unified-pagination-container');
    
    // If container is not already a unified-pagination-container, wrap in one
    // Otherwise, use the container directly
    let html = '';
    if (!isAlreadyUnifiedContainer) {
        html = '<div class="unified-pagination-container"';
        html += ` data-current-page="${page}" data-total-pages="${totalPagesFinal}"`;
        if (metadata.hasTotalItems) html += ` data-total-items="${metadata.totalItems}"`;
        if (metadata.hasPageSize) html += ` data-page-size="${metadata.pageSize}"`;
        if (endpoint) html += ` data-endpoint="${escapeAttr(endpoint)}"`;
        html += '>';
    } else {
        // Update data attributes on existing container
        container.setAttribute('data-current-page', page);
        container.setAttribute('data-total-pages', totalPagesFinal);
        if (metadata.hasTotalItems) container.setAttribute('data-total-items', metadata.totalItems);
        if (metadata.hasPageSize) container.setAttribute('data-page-size', metadata.pageSize);
        if (endpoint) container.setAttribute('data-endpoint', endpoint);
    }

    // Pagination info
    if (showInfo) {
        html += '<div class="unified-pagination-info">';
        html += '<span class="pagination-text">';
        html += '<i class="bi bi-info-circle me-1" aria-hidden="true"></i>';
        html += `${escapeHtml(metadata.pageLabel)} <strong>${formatNumber(page)}</strong> ${escapeHtml(metadata.ofLabel)} <strong>${formatNumber(totalPagesFinal)}</strong>`;
        if (metadata.rangeLabel) {
            html += `<span class="pagination-range">${escapeHtml(metadata.rangeLabel)}</span>`;
        }
        html += '</span>';
        html += '</div>';
    }

    // Pagination controls
    html += '<div class="unified-pagination-controls">';
    html += `<nav aria-label="${escapeAttr(label(labels, 'pageNavigation', 'Page navigation'))}">`;
    html += '<ul class="unified-pagination-list">';

    // First button
    html += '<li class="unified-pagination-item">';
    html += `<a class="unified-pagination-link ${page <= 1 ? 'disabled' : ''}" `;
    html += `href="${page > 1 ? buildPageUrl(1, endpoint, baseUrl, urlParams, onPageChange) : '#'}" `;
    html += `aria-label="${escapeAttr(label(labels, 'firstPage', 'First Page'))}" `;
    if (page <= 1) html += 'aria-disabled="true" tabindex="-1"';
    html += '>';
    html += '<i class="bi bi-chevron-double-left" aria-hidden="true"></i>';
    html += `<span class="d-none d-sm-inline ms-1">${escapeHtml(label(labels, 'first', 'First'))}</span>`;
    html += '</a></li>';

    // Previous button
    html += '<li class="unified-pagination-item">';
    html += `<a class="unified-pagination-link ${page <= 1 ? 'disabled' : ''}" `;
    html += `href="${page > 1 ? buildPageUrl(page - 1, endpoint, baseUrl, urlParams, onPageChange) : '#'}" `;
    html += `aria-label="${escapeAttr(label(labels, 'previousPage', 'Previous Page'))}" `;
    if (page <= 1) html += 'aria-disabled="true" tabindex="-1"';
    html += '>';
    html += '<i class="bi bi-chevron-left" aria-hidden="true"></i>';
    html += `<span class="d-none d-sm-inline ms-1">${escapeHtml(label(labels, 'previous', 'Previous'))}</span>`;
    html += '</a></li>';

    // First page and ellipsis
    if (startPage > 1) {
        html += '<li class="unified-pagination-item">';
        html += `<a class="unified-pagination-link" href="${buildPageUrl(1, endpoint, baseUrl, urlParams, onPageChange)}">1</a>`;
        html += '</li>';
        if (startPage > 2) {
            html += '<li class="unified-pagination-item disabled">';
            html += '<span class="unified-pagination-ellipsis" aria-hidden="true">…</span>';
            html += '</li>';
        }
    }

    // Page numbers
    for (let p = startPage; p <= endPage; p++) {
        html += '<li class="unified-pagination-item';
        if (p === page) html += ' active';
        html += '">';
        if (p === page) {
            html += `<span class="unified-pagination-link active" aria-current="page">${p}</span>`;
        } else {
            html += `<a class="unified-pagination-link" href="${buildPageUrl(p, endpoint, baseUrl, urlParams, onPageChange)}">${p}</a>`;
        }
        html += '</li>';
    }

    // Last page and ellipsis
    if (endPage < totalPagesFinal) {
        if (endPage < totalPagesFinal - 1) {
            html += '<li class="unified-pagination-item disabled">';
            html += '<span class="unified-pagination-ellipsis" aria-hidden="true">…</span>';
            html += '</li>';
        }
        html += '<li class="unified-pagination-item">';
        html += `<a class="unified-pagination-link" href="${buildPageUrl(totalPagesFinal, endpoint, baseUrl, urlParams, onPageChange)}">${totalPagesFinal}</a>`;
        html += '</li>';
    }

    // Next button
    html += '<li class="unified-pagination-item">';
    html += `<a class="unified-pagination-link ${page >= totalPagesFinal ? 'disabled' : ''}" `;
    html += `href="${page < totalPagesFinal ? buildPageUrl(page + 1, endpoint, baseUrl, urlParams, onPageChange) : '#'}" `;
    html += `aria-label="${escapeAttr(label(labels, 'nextPage', 'Next Page'))}" `;
    if (page >= totalPagesFinal) html += 'aria-disabled="true" tabindex="-1"';
    html += '>';
    html += `<span class="d-none d-sm-inline me-1">${escapeHtml(label(labels, 'next', 'Next'))}</span>`;
    html += '<i class="bi bi-chevron-right" aria-hidden="true"></i>';
    html += '</a></li>';

    // Last button
    html += '<li class="unified-pagination-item">';
    html += `<a class="unified-pagination-link ${page >= totalPagesFinal ? 'disabled' : ''}" `;
    html += `href="${page < totalPagesFinal ? buildPageUrl(totalPagesFinal, endpoint, baseUrl, urlParams, onPageChange) : '#'}" `;
    html += `aria-label="${escapeAttr(label(labels, 'lastPage', 'Last Page'))}" `;
    if (page >= totalPagesFinal) html += 'aria-disabled="true" tabindex="-1"';
    html += '>';
    html += `<span class="d-none d-sm-inline me-1">${escapeHtml(label(labels, 'last', 'Last'))}</span>`;
    html += '<i class="bi bi-chevron-double-right" aria-hidden="true"></i>';
    html += '</a></li>';

    html += '</ul></nav>';

    // Jump to page
    if (showJump && totalPagesFinal > 5) {
        const jumpId = `jumpToPageInput-${containerId}`;
        html += '<div class="unified-pagination-jump">';
        html += `<label for="${jumpId}" class="visually-hidden">${escapeHtml(label(labels, 'jumpToPage', 'Jump to page'))}</label>`;
        html += `<input type="number" id="${jumpId}" class="form-control form-control-sm unified-pagination-jump-input" `;
        html += `min="1" max="${totalPagesFinal}" value="${page}" placeholder="${escapeAttr(metadata.pageLabel)}" `;
        html += `data-total-pages="${totalPagesFinal}">`;
        html += '<button type="button" class="btn btn-sm btn-outline-primary unified-pagination-jump-btn" ';
        html += `data-container-id="${escapeAttr(containerId)}" aria-label="${escapeAttr(label(labels, 'goToPage', 'Go to page'))}">`;
        html += '<i class="bi bi-arrow-right"></i>';
        html += '</button>';
        html += '</div>';
    }

    html += '</div>';
    if (!isAlreadyUnifiedContainer) {
        html += '</div>';
    }

    if (isAlreadyUnifiedContainer) {
        // If container is already unified-pagination-container, replace only the inner content
        // Clear existing content first
        container.innerHTML = '';
        // Then add the new content
        container.insertAdjacentHTML('beforeend', html);
        // Update data attributes
        container.setAttribute('data-current-page', page);
        container.setAttribute('data-total-pages', totalPagesFinal);
        if (metadata.hasTotalItems) container.setAttribute('data-total-items', metadata.totalItems);
        if (metadata.hasPageSize) container.setAttribute('data-page-size', metadata.pageSize);
        if (endpoint) container.setAttribute('data-endpoint', endpoint);
    } else {
        container.innerHTML = html;
    }
    
    // Mark container to prevent duplicate listeners
    if (!container.dataset.paginationInitialized) {
        container.dataset.paginationInitialized = 'true';
    }

    // Attach event listeners after a brief delay to ensure DOM is ready
    setTimeout(() => {
        attachPaginationListeners(container, onPageChange, endpoint, baseUrl, urlParams);
    }, 0);
}

function getPageWindow(currentPage, totalPages, visiblePageCount = 5) {
    const maxVisible = Math.max(1, Math.floor(Number(visiblePageCount) || 5));
    let startPage = Math.max(1, currentPage - Math.floor(maxVisible / 2));
    let endPage = Math.min(totalPages, startPage + maxVisible - 1);
    startPage = Math.max(1, endPage - maxVisible + 1);
    return { startPage, endPage };
}

function buildPaginationMetadata({ page, totalPages, totalItems, pageSize, itemLabel, labels }) {
    const pageLabel = label(labels, 'page', 'Page');
    const ofLabel = label(labels, 'of', 'of');
    const showingLabel = label(labels, 'showing', 'Showing');
    const safeItemLabel = label(labels, 'itemLabel', itemLabel || 'records');
    const parsedTotal = Number(totalItems);
    const parsedPageSize = Number(pageSize);
    const hasTotalItems = Number.isFinite(parsedTotal) && parsedTotal >= 0;
    const hasPageSize = Number.isFinite(parsedPageSize) && parsedPageSize > 0;
    let rangeLabel = '';

    if (hasTotalItems && hasPageSize) {
        const total = Math.floor(parsedTotal);
        const size = Math.floor(parsedPageSize);
        const start = total > 0 ? ((page - 1) * size) + 1 : 0;
        const end = total > 0 ? Math.min(page * size, total) : 0;
        rangeLabel = ` · ${showingLabel} ${formatNumber(start)}–${formatNumber(end)} ${ofLabel} ${formatNumber(total)} ${safeItemLabel}`;
    }

    return {
        pageLabel,
        ofLabel,
        rangeLabel,
        hasTotalItems,
        totalItems: hasTotalItems ? Math.floor(parsedTotal) : null,
        hasPageSize,
        pageSize: hasPageSize ? Math.floor(parsedPageSize) : null,
        totalPages
    };
}

function label(labels, key, fallback) {
    return labels && labels[key] ? String(labels[key]) : String(fallback);
}

function formatNumber(value) {
    const numeric = Number(value);
    if (!Number.isFinite(numeric)) return String(value ?? '');
    return numeric.toLocaleString();
}

function escapeHtml(value) {
    const div = document.createElement('div');
    div.textContent = value == null ? '' : String(value);
    return div.innerHTML;
}

function escapeAttr(value) {
    return String(value == null ? '' : value)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

/**
 * Build URL for a specific page
 */
function buildPageUrl(page, endpoint, baseUrl, urlParams, onPageChange) {
    if (onPageChange) {
        // Use callback function
        return `#page-${page}`;
    }

    if (endpoint) {
        // Build URL using endpoint
        const params = new URLSearchParams();
        params.set('page', page);
        Object.keys(urlParams).forEach(key => {
            if (key !== 'page' && urlParams[key] !== null && urlParams[key] !== undefined && urlParams[key] !== '') {
                params.set(key, urlParams[key]);
            }
        });
        // Preserve current URL params
        const currentParams = new URLSearchParams(window.location.search);
        currentParams.forEach((value, key) => {
            if (key !== 'page' && !(key in urlParams)) {
                params.set(key, value);
            }
        });
        return `?${params.toString()}`;
    }

    if (baseUrl) {
        // Build URL using base URL
        const url = new URL(baseUrl, window.location.origin);
        url.searchParams.set('page', page);
        Object.keys(urlParams).forEach(key => {
            if (key !== 'page' && urlParams[key] !== null && urlParams[key] !== undefined && urlParams[key] !== '') {
                url.searchParams.set(key, urlParams[key]);
            }
        });
        return url.pathname + url.search;
    }

    // Fallback: use current URL
    const url = new URL(window.location.href);
    url.searchParams.set('page', page);
    Object.keys(urlParams).forEach(key => {
        if (key !== 'page' && urlParams[key] !== null && urlParams[key] !== undefined && urlParams[key] !== '') {
            url.searchParams.set(key, urlParams[key]);
        }
    });
    return url.pathname + url.search;
}

/**
 * Attach event listeners to pagination
 */
function attachPaginationListeners(container, onPageChange, endpoint, baseUrl, urlParams) {
    // Store the callback in the container for event delegation. Clear stale
    // callbacks when a container switches back to URL-driven pagination.
    if (onPageChange && typeof onPageChange === 'function') {
        container._paginationCallback = onPageChange;
    } else {
        delete container._paginationCallback;
    }
    
    // Use event delegation on the container for better reliability
    // Only attach once per container
    if (!container._paginationDelegationAttached) {
        container.addEventListener('click', (e) => {
            // Find the closest pagination link
            const link = e.target.closest('.unified-pagination-link');
            if (!link) return;
            
            e.preventDefault();
            e.stopPropagation();
            
            // Don't process if disabled or active
            if (link.classList.contains('disabled') || link.classList.contains('active')) {
                return;
            }
            
            const href = link.getAttribute('href');
            if (href && href.startsWith('#page-')) {
                const page = parseInt(href.replace('#page-', ''));
                if (!isNaN(page) && container._paginationCallback && typeof container._paginationCallback === 'function') {
                    container._paginationCallback(page);
                }
            } else if (href && href !== '#') {
                // Navigate to URL (for server-side pagination)
                window.location.href = href;
            }
        });
        container._paginationDelegationAttached = true;
    } else {
        // Update the callback if it changed
        if (onPageChange && typeof onPageChange === 'function') {
            container._paginationCallback = onPageChange;
        }
    }
    
    // Direct listeners are not needed since event delegation handles everything
    // The delegation listener persists even when innerHTML is replaced

    // Handle jump to page
    const jumpInput = container.querySelector('.unified-pagination-jump-input');
    const jumpBtn = container.querySelector('.unified-pagination-jump-btn');
    
    if (jumpInput && jumpBtn) {
        const handleJump = () => {
            let targetPage = parseInt(jumpInput.value);
            const totalPages = parseInt(jumpInput.getAttribute('data-total-pages')) || 1;
            
            if (isNaN(targetPage) || targetPage < 1) {
                targetPage = 1;
            } else if (targetPage > totalPages) {
                targetPage = totalPages;
            }
            
            if (onPageChange && typeof onPageChange === 'function') {
                onPageChange(targetPage);
            } else {
                const url = buildPageUrl(targetPage, endpoint, baseUrl, urlParams, onPageChange);
                if (url.startsWith('#')) {
                    // Callback-based, trigger callback
                    if (onPageChange) onPageChange(targetPage);
                } else {
                    window.location.href = url;
                }
            }
        };

        jumpBtn.addEventListener('click', handleJump);
        jumpInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                handleJump();
            }
        });
    }
}

// Make available globally
window.renderUnifiedPagination = renderUnifiedPagination;

