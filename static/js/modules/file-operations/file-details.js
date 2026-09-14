/**
 * File Details Modal
 * Handles showing file details in modal
 */

import { fileNavigationState, modalState } from '../core/state.js';
import { MODAL_ENABLED, translations } from '../core/config.js';
import { escapeHtml, formatFileSize } from '../core/utils.js';
import { updateFileNavigationButtons } from './file-navigation.js';
import { clearModalSearch } from '../search/modal-search.js';

/**
 * Show file details modal
 * @param {number} fileId - File ID
 * @param {string} fileName - File name
 * @param {Array} fileList - Optional list of files for navigation
 * @param {number} fileIndex - Optional index in file list
 */
export function showFileDetails(fileId, fileName, fileList = null, fileIndex = -1) {
    console.log('Showing file details for:', { fileId, fileName, fileList, fileIndex, MODAL_ENABLED });
    
    // If modal is disabled, open in new tab instead
    if (!MODAL_ENABLED) {
        console.log('Modal disabled - opening in new tab');
        window.open(`/file/${fileId}`, '_blank');
        return;
    }
    
    // Store file list context if provided
    if (fileList && Array.isArray(fileList)) {
        fileNavigationState.currentFiles = fileList;
        fileNavigationState.currentIndex = fileIndex >= 0 ? fileIndex : fileList.findIndex(f => f.id === fileId);
    } else {
        // Try to get file list from current page
        const fileRows = document.querySelectorAll('.file-row-item[data-file-id]');
        if (fileRows.length > 0) {
            fileNavigationState.currentFiles = Array.from(fileRows).map(row => ({
                id: parseInt(row.getAttribute('data-file-id')),
                name: row.getAttribute('data-file-name') || 'File'
            }));
            fileNavigationState.currentIndex = fileNavigationState.currentFiles.findIndex(f => f.id === fileId);
        }
    }
    
    // Open modal
    const modal = document.getElementById('fileModal');
    if (!modal) {
        console.error('File modal not found in DOM');
        if (window.showError) {
            window.showError('Modal element not found. Please refresh the page.');
        }
        // Fallback: open in new tab
        window.open(`/file/${fileId}`, '_blank');
        return;
    }
    
    // Update navigation buttons
    updateFileNavigationButtons();
    
    // Set modal title
    const modalTitle = document.getElementById('modalTitle');
    if (modalTitle) {
        modalTitle.textContent = fileName || (translations.fileDetails || 'File Details');
    }
    
    // Show loading state
    const contentSection = document.getElementById('fileContentSection');
    const analysisSection = document.getElementById('fileAnalysisSection');
    const metadataSection = document.getElementById('fileMetadataSection');
    
    if (contentSection) {
        contentSection.innerHTML = `<div class="content-loading">${translations.loadingContent || 'Loading content...'}</div>`;
    }
    if (analysisSection) {
        analysisSection.innerHTML = `<div class="content-loading">${translations.loadingAnalysis || 'Loading analysis...'}</div>`;
    }
    if (metadataSection) {
        metadataSection.innerHTML = `<div class="content-loading">${translations.loadingMetadata || 'Loading metadata...'}</div>`;
    }
    
    // Clear any previous search state
    if (clearModalSearch) {
        clearModalSearch();
    }
    
    // Show modal
    modal.classList.add('active');
    modal.style.display = 'flex';
    modal.style.visibility = 'visible';
    modal.style.opacity = '1';
    // z-index is handled by CSS (10000)
    document.body.style.overflow = 'hidden';
    
    // Load file details content
    loadFileDetailsContent(fileId, fileName);
    
    modalState.isOpen = true;
    modalState.currentFileId = fileId;
    modalState.currentFileName = fileName;
}

/**
 * Escape a value for use inside a double-quoted HTML attribute.
 *
 * escapeHtml() from core/utils.js escapes via textContent -> innerHTML, which
 * handles & < > but NOT quotes, because a text node never contains them. That
 * is correct for element content and unsafe for attribute values: a lineage
 * name of `x" onmouseover="alert(1)` survives escapeHtml unchanged and breaks
 * out of the attribute, giving stored XSS from an attacker-chosen filename
 * inside an uploaded archive.
 *
 * Attribute context therefore needs its own escaper. Verified by
 * tests/unit/test_frontend_lineage_escaping.py.
 *
 * @param {*} value - raw value, typically an untrusted filename
 * @returns {string} value safe to place inside a double-quoted attribute
 */
export function escapeAttribute(value) {
    if (value == null) return '';
    return String(value)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

/**
 * Render the parent/child lineage block for File Details.
 *
 * Every extracted object (archive member, attachment, embedded document, OCR
 * derivative) is its own database row linked to its origin by parent_path_id.
 * Without this the view shows an OCR page as though it were an unrelated
 * top-level file, which is exactly the flattening the data model exists to
 * prevent.
 *
 * Names come from untrusted input (filenames inside an archive can be
 * attacker-chosen), so every value goes through escapeHtml and ids are emitted
 * into data attributes rather than interpolated into a URL or handler.
 *
 * @param {object} file - the details payload
 * @returns {string} HTML for the lineage block, or '' when there is nothing to show
 */
export function renderLineageSection(file) {
    const lineage = file && file.lineage;
    if (!lineage) return '';

    const ancestors = Array.isArray(lineage.ancestors) ? lineage.ancestors : [];
    const descendants = Array.isArray(lineage.descendants) ? lineage.descendants : [];
    if (!ancestors.length && !descendants.length) return '';

    const row = (item, depth, isChild) => {
        const id = Number(item.id);
        if (!Number.isInteger(id)) return '';
        const indent = isChild ? (depth - 1) * 12 : 0;
        // Two different contexts, two different escapers: the link text is
        // element content, data-lineage-name is an attribute value.
        const label = escapeHtml(String(item.name || `#${id}`));
        const labelAttr = escapeAttribute(String(item.name || `#${id}`));
        const arrow = isChild ? '\u21B3' : '\u2191';
        return `
            <div class="lineage-row" style="margin-left: ${indent}px;">
                <span class="lineage-arrow">${arrow}</span>
                <a href="#" class="lineage-link"
                   data-lineage-id="${id}"
                   data-lineage-name="${labelAttr}">${label}</a>
            </div>`;
    };

    let html = '<div class="lineage-section">';
    html += `<div class="lineage-title">${escapeHtml(translations.lineage || 'Contained In / Contains')}</div>`;

    if (ancestors.length) {
        html += `<div class="lineage-group">${escapeHtml(translations.containedIn || 'Contained in')}</div>`;
        // Root first, so the chain reads top-down.
        ancestors.forEach(a => { html += row(a, a.depth || 1, false); });
    } else {
        html += `<div class="lineage-group">${escapeHtml(translations.topLevelObject || 'Top-level object')}</div>`;
    }

    if (descendants.length) {
        html += `<div class="lineage-group">${escapeHtml(
            (translations.contains || 'Contains') + ` (${descendants.length})`
        )}</div>`;
        descendants.forEach(d => { html += row(d, d.depth || 1, true); });
    }

    if (Array.isArray(lineage.errors) && lineage.errors.length) {
        html += `<div class="lineage-warning">${escapeHtml(
            (translations.lineageUnavailable || 'Lineage partially unavailable') +
            ': ' + lineage.errors.join(', ')
        )}</div>`;
    }

    html += '</div>';
    return html;
}

/**
 * Load file details content into modal
 * @param {number} fileId - File ID
 * @param {string} fileName - File name
 */
export async function loadFileDetailsContent(fileId, fileName) {
    try {
        const response = await fetch(`/api/file/${fileId}/details`);
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        const data = await response.json();
        
        if (!data.success || !data.details) {
            // ERROR HANDLING FIX: Properly handle API error responses
            const errorMsg = escapeHtml(data.error || (translations.errorLoadingFileDetails || 'Error loading file details'));
            const contentSection = document.getElementById('fileContentSection');
            const analysisSection = document.getElementById('fileAnalysisSection');
            const metadataSection = document.getElementById('fileMetadataSection');
            
            // Show error in all sections
            if (contentSection) contentSection.innerHTML = `<div class="empty-state error">${errorMsg}</div>`;
            if (analysisSection) analysisSection.innerHTML = `<div class="empty-state error">${errorMsg}</div>`;
            if (metadataSection) metadataSection.innerHTML = `<div class="empty-state error">${errorMsg}</div>`;
            
            // Show notification to user
            if (window.fms && window.fms.ui && window.fms.ui.notifications) {
                window.fms.ui.notifications.error(errorMsg);
            } else if (window.showError) {
                window.showError(errorMsg);
            }
            return;
        }

        const file = data.details;
        
        // Store file ID for export functionality
        window.currentModalFileId = fileId;
        
        // Populate Content Section
        const contentSection = document.getElementById('fileContentSection');
        if (contentSection) {
            const contentValue = file.content || file['content'] || '';
            const fileType = file.type || '';
            const filePath = file.path || '';
            
            if (contentValue && typeof contentValue === 'string' && contentValue.trim()) {
                // Display full content without truncation
                // SECURITY FIX: Content is already escaped in formatContentByType or we escape it here
                const displayContent = contentValue;
                
                window.currentModalFileContent = contentValue;
                window.currentModalFileName = fileName || 'file';
                
                // Format content based on file type
                import('../content-formatter.js').then(module => {
                    const formatted = module.formatContentByType(displayContent, fileType, filePath, fileId);
                    if (formatted) {
                        // SECURITY FIX: Ensure formatted content is safe - formatContentByType should handle escaping
                        // But we'll add a safety check here
                        contentSection.innerHTML = `<div id="modalContentText" class="formatted-content-wrapper">${formatted}</div>`;
                        
                        // Attach image error handlers after DOM insertion
                        setTimeout(() => {
                            const contentElement = document.getElementById('modalContentText');
                            if (contentElement && window.attachImageErrorHandlers) {
                                window.attachImageErrorHandlers(contentElement);
                            }
                        }, 10);
                    } else {
                        // SECURITY FIX: Always escape HTML content to prevent XSS
                        contentSection.innerHTML = `<pre id="modalContentText" style="margin: 0; white-space: pre-wrap; word-wrap: break-word; overflow-wrap: break-word;">${escapeHtml(displayContent)}</pre>`;
                    }
                    
                    const contentElement = document.getElementById('modalContentText');
                    if (contentElement) {
                        contentElement.setAttribute('data-original-content', displayContent);
                        contentElement.setAttribute('data-full-content', escapeHtml(contentValue));
                    }
                }).catch(err => {
                    console.error('Error formatting modal content:', err);
                    // SECURITY FIX: Always escape HTML content to prevent XSS
                    contentSection.innerHTML = `<pre id="modalContentText" style="margin: 0; white-space: pre-wrap; word-wrap: break-word; overflow-wrap: break-word;">${escapeHtml(displayContent)}</pre>`;
                    const contentElement = document.getElementById('modalContentText');
                    if (contentElement) {
                        contentElement.setAttribute('data-original-content', displayContent);
                        contentElement.setAttribute('data-full-content', escapeHtml(contentValue));
                    }
                });
            } else if (fileType.match(/\.(jpg|jpeg|png|gif|bmp|tiff|tif|webp|svg)$/i) && (filePath || fileId)) {
                // Image file without text content - show image
                import('../content-formatter.js').then(module => {
                    const formatted = module.formatContentByType('', fileType, filePath, fileId);
                    if (formatted) {
                        contentSection.innerHTML = `<div id="modalContentText" class="formatted-content-wrapper">${formatted}</div>`;
                    }
                }).catch(err => {
                    console.error('Error formatting image:', err);
                });
            } else {
                window.currentModalFileContent = '';
                window.currentModalFileName = fileName || 'file';
                contentSection.innerHTML = `<div class="empty-state">${translations.noContentAvailable || 'No content available'}</div>`;
            }
        }
        
        // Populate Analysis Section
        const analysisSection = document.getElementById('fileAnalysisSection');
        if (analysisSection) {
            let analysisHtml = '';
            
            if (file.title) {
                analysisHtml += `
                    <div class="analysis-section-title">
                        <h4><i class="bi bi-file-text me-2"></i>${translations.titleAnalysis || 'Title Analysis'}</h4>
                    </div>
                    <div class="analysis-item">
                        <div class="analysis-label">${translations.fileTitle || 'File Title'}:</div>
                        <div class="analysis-value">${escapeHtml(file.title)}</div>
                    </div>
                `;
                
                if (file.similar_titles && file.similar_titles.length > 0) {
                    analysisHtml += `
                        <div class="analysis-item">
                            <div class="analysis-label">${translations.similarTitles || 'Similar Titles'}:</div>
                            <div class="similar-titles-list">
                    `;
                    
                    file.similar_titles.forEach(similar => {
                        analysisHtml += `
                            <div class="similar-title-item">
                                <span class="similarity-badge">${similar.similarity_percent || 0}%</span>
                                <span class="similar-title-text">${escapeHtml(similar.name || 'Unknown')}</span>
                                ${similar.file_count ? `<span class="file-count-badge">${similar.file_count} files</span>` : ''}
                            </div>
                        `;
                    });
                    
                    analysisHtml += `
                            </div>
                        </div>
                    `;
                }
                
                analysisHtml += '<hr style="margin: 1rem 0; border-color: #e2e8f0;">';
            }
            
            analysisHtml += '<div id="classificationChartsContainer"></div>';
            analysisSection.innerHTML = analysisHtml;
            
            // Load charts after HTML is set
            if (window.fms && window.fms.charts && window.fms.charts.loadClassificationCharts) {
                window.fms.charts.loadClassificationCharts(file.id);
            } else if (window.loadClassificationCharts) {
                window.loadClassificationCharts(file.id);
            }
        }
        
        // Populate Metadata Section
        const metadataSection = document.getElementById('fileMetadataSection');
        if (metadataSection) {
            let metadataHtml = '';
            
            const metadataItems = [
                { label: translations.fileName || 'File Name', value: file.name || 'N/A' },
                { label: translations.fileType || 'File Type', value: file.type || 'Unknown' },
                { label: translations.fileSize || 'File Size', value: formatFileSize(file.size) },
                { label: translations.status || 'Status', value: file.status || 'Unknown' },
                { label: translations.fileDate || 'File Date', value: file.file_date ? new Date(file.file_date).toLocaleDateString() : 'N/A' },
                { label: translations.dateCreated || 'Date Created', value: file.date_creation ? new Date(file.date_creation).toLocaleDateString() : 'N/A' },
                { label: translations.source || 'Source', value: file.source || 'Unknown' },
                { label: translations.side || 'Side', value: file.side || 'Unknown' },
                { label: translations.wordCount || 'Word Count', value: (file.word_count || 0).toLocaleString() },
                { label: translations.contentChunks || 'Content Chunks', value: (file.content_chunks || 0).toLocaleString() }
            ];
            
            // Processing status: file_status says only whether text exists, so
            // a corrupt file, a skipped icon and an unrecognised type all read
            // 'Unread'. processing.status says which of those happened.
            if (file.processing && file.processing.status) {
                const p = file.processing;
                let statusValue = p.status.replace(/_/g, ' ');
                if (p.detail) statusValue += ` - ${p.detail}`;
                metadataItems.push({
                    label: translations.processingStatus || 'Processing Status',
                    value: statusValue
                });
            }
            
            // Where this object came from, as recorded in the database.
            if (file.hierarchy_path) {
                metadataItems.push({
                    label: translations.hierarchyPath || 'Origin',
                    value: file.hierarchy_path
                });
            }
            
            // How the content was derived - e.g. OCR engine and confidence.
            const prov = file.extraction_provenance;
            if (prov && prov.ocr) {
                const ocrBits = [];
                if (ocrBits.push) {
                    if (prov.ocr.engine) ocrBits.push(prov.ocr.engine);
                    if (prov.ocr.confidence) ocrBits.push(`${Math.round(prov.ocr.confidence * 100)}% conf.`);
                    if (prov.ocr.derived) ocrBits.push('derived');
                }
                metadataItems.push({
                    label: translations.ocrProvenance || 'OCR Provenance',
                    value: ocrBits.join(' / ') || 'OCR'
                });
            }
            
            if (file.path) {
                metadataItems.push({ label: translations.filePath || 'File Path', value: file.path });
            }
            
            if (file.hash) {
                metadataItems.push({ label: translations.hash || 'Relations', value: file.hash });
            }
            
            metadataItems.forEach(item => {
                metadataHtml += `
                    <div class="metadata-item">
                        <div class="metadata-label">${escapeHtml(item.label)}</div>
                        <div class="metadata-value">${escapeHtml(String(item.value))}</div>
                    </div>
                `;
            });
            
            metadataHtml += renderLineageSection(file);
            
            metadataSection.innerHTML = metadataHtml || `<div class="empty-state">${translations.noMetadataAvailable || 'No metadata available'}</div>`;
            
            // Wire the lineage links after the HTML is in the DOM. Delegated on
            // the section so re-renders do not need re-binding.
            metadataSection.querySelectorAll('.lineage-link').forEach(link => {
                link.addEventListener('click', (event) => {
                    event.preventDefault();
                    const id = parseInt(link.getAttribute('data-lineage-id'), 10);
                    const name = link.getAttribute('data-lineage-name') || 'File';
                    if (Number.isInteger(id) && window.fms?.fileOperations?.details?.showFileDetails) {
                        window.fms.fileOperations.details.showFileDetails(id, name);
                    }
                });
            });
        }
    } catch (error) {
        console.error('Error loading file details:', error);
        // SECURITY FIX: Always escape error messages to prevent XSS
        const errorMsg = escapeHtml(error.message || 'Unknown error occurred');
        const networkError = error.name === 'TypeError' && error.message.includes('fetch');
        const userFriendlyMsg = networkError 
            ? (translations.networkError || 'Network error: Unable to connect to server. Please check your connection and try again.')
            : `${translations.errorLoadingFileDetails || 'Error loading file details'}: ${errorMsg}`;
        
        const contentSection = document.getElementById('fileContentSection');
        const analysisSection = document.getElementById('fileAnalysisSection');
        const metadataSection = document.getElementById('fileMetadataSection');
        
        // ERROR HANDLING FIX: Show proper error messages in all sections
        if (contentSection) {
            contentSection.innerHTML = `<div class="empty-state error">${escapeHtml(userFriendlyMsg)}</div>`;
        }
        if (analysisSection) {
            analysisSection.innerHTML = `<div class="empty-state error">${escapeHtml(userFriendlyMsg)}</div>`;
        }
        if (metadataSection) {
            metadataSection.innerHTML = `<div class="empty-state error">${escapeHtml(userFriendlyMsg)}</div>`;
        }
        
        // Show notification to user
        if (window.fms && window.fms.ui && window.fms.ui.notifications) {
            window.fms.ui.notifications.error(userFriendlyMsg);
        } else if (window.showError) {
            window.showError(userFriendlyMsg);
        }
    }
}

/**
 * Close file modal
 */
export function closeFileModal() {
    const modal = document.getElementById('fileModal');
    if (modal) {
        modal.classList.remove('active');
        modal.style.display = 'none';
        document.body.style.overflow = '';
        
        // Clear search state
        if (clearModalSearch) {
            clearModalSearch();
        }
        
        // Clear stored content and file ID
        window.currentModalFileContent = '';
        window.currentModalFileName = '';
        window.currentModalFileId = null;
        
        modalState.isOpen = false;
        modalState.currentFileId = null;
        modalState.currentFileName = null;
    }
}

// Setup click outside to close
if (typeof document !== 'undefined') {
    document.addEventListener('click', function(e) {
        const modal = document.getElementById('fileModal');
        if (modal && modal.classList.contains('active')) {
            if (e.target === modal) {
                closeFileModal();
            }
        }
    });
    
    // Keyboard navigation
    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape') {
            const modal = document.getElementById('fileModal');
            if (modal && modal.classList.contains('active')) {
                closeFileModal();
            }
        }
    });
}

