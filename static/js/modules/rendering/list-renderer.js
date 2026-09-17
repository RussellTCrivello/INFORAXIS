/**
 * List View Renderer (shared helpers imported from grid renderer)
 */

import { escapeHtml } from '../core/utils.js';
import { translations, sectionLabels } from '../core/config.js';
import { renderSectionPaginationControls } from './pagination.js';
import { getItemDetails, getSectionIcon } from './grid-renderer.js';

export function renderListView(items, section, showPagination = false) {
    const sectionLabel = sectionLabels[section] || section;
    // Reuse add-button helper by delegating to grid-renderer (kept minimal here)
    const addButtonHtml = ''; // add buttons handled in grid renderer; safe to omit in list

    let html = '<div class="section">';
    html += '<div class="section-header">';
    html += `<div class="section-label"><i class="bi bi-${getSectionIcon(section)}"></i> ${sectionLabel}</div>`;
    html += addButtonHtml;
    html += '</div>';
    html += '<div class="files-list-view ia-data-scroll-region">';

    if (items.length === 0) {
        html += `<div class="empty-state list-empty-state">${translations.noItemsFound || 'No items found'}</div>`;
    } else {
        items.forEach(item => {
            // For addresses, use the exact database value without any transformation
            let displayName;
            if (section === 'address') {
                displayName = item.name || 'Unknown Address';
            } else if (section === 'geolocation') {
                // For geolocation, show coordinates as the main display name if available
                // Helper function to format coordinates with proper direction indicators
                const formatCoords = (lat, lon) => {
                    const latNum = parseFloat(lat);
                    const lonNum = parseFloat(lon);
                    const latDir = latNum >= 0 ? 'N' : 'S';
                    const lonDir = lonNum >= 0 ? 'E' : 'W';
                    const latFormatted = Math.abs(latNum).toFixed(6);
                    const lonFormatted = Math.abs(lonNum).toFixed(6);
                    return `📍 ${latFormatted}°${latDir}, ${lonFormatted}°${lonDir}`;
                };
                
                if (item.latitude !== null && item.latitude !== undefined && 
                    item.longitude !== null && item.longitude !== undefined) {
                    displayName = formatCoords(item.latitude, item.longitude);
                } else if (item.coordinates) {
                    const coords = item.coordinates.trim();
                    const coordMatch = coords.match(/^(-?\d+\.?\d*)\s*,\s*(-?\d+\.?\d*)$/);
                    if (coordMatch) {
                        displayName = formatCoords(coordMatch[1], coordMatch[2]);
                    } else {
                        displayName = `📍 GPS: ${coords}`;
                    }
                } else {
                    displayName = item.name_display || item.name || 'Unknown Location';
                }
            } else {
                displayName = item.name_display || (
                    section === 'hash' && item.name && item.name.length > 32
                        ? item.name.substring(0, 32) + '...'
                        : (item.name || 'Unnamed')
                );
            }
            const details = getItemDetails(item, section);
            const itemId = item.id || item.ID || null;
            if (!itemId) return;

            const safeDisplayName = escapeHtml(displayName).replace(/"/g, '&quot;');
            let groupIndicator = '';
            if (item.is_group && section === 'titles') {
                groupIndicator = `<span class="badge bg-info ms-2" title="${item.is_identical ? 'Identical' : 'Similar'} titles group">${item.group_count}</span>`;
            }

            let groupDataAttr = '';
            if (item.is_group && section === 'titles' && item.similar_titles) {
                const titleIds = item.similar_titles.map(st => st.id).filter(id => id).join(',');
                groupDataAttr = `data-group-title-ids="${titleIds}"`;
            }

            // Generate copy button for geolocation coordinates
            let copyButtonHtml = '';
            if (section === 'geolocation') {
                // Check if we have valid coordinates to copy
                const hasCoords = (item.latitude !== null && item.latitude !== undefined && 
                                  item.longitude !== null && item.longitude !== undefined) ||
                                 (item.coordinates && item.coordinates.trim());
                
                if (hasCoords) {
                    // Pass both latitude/longitude and raw coordinates string
                    // The copy function will normalize it properly
                    const lat = item.latitude !== null && item.latitude !== undefined ? item.latitude : '';
                    const lon = item.longitude !== null && item.longitude !== undefined ? item.longitude : '';
                    const coordsStr = item.coordinates || '';
                    
                    // Escape for HTML attribute
                    const safeLat = escapeHtml(String(lat)).replace(/"/g, '&quot;');
                    const safeLon = escapeHtml(String(lon)).replace(/"/g, '&quot;');
                    const safeCoords = escapeHtml(coordsStr).replace(/"/g, '&quot;');
                    
                    // If we have parsed lat/lon, pass them; otherwise pass the string
                    if (lat !== '' && lon !== '') {
                        copyButtonHtml = `
                            <button class="btn btn-sm btn-outline-secondary geolocation-copy-btn" 
                                    onclick="event.stopPropagation(); copyGeolocationCoordinates('${safeLat}', this, '${safeLon}');"
                                    title="${translations.copyCoordinates || 'Copy coordinates'}"
                                    aria-label="${translations.copyCoordinates || 'Copy coordinates'}">
                                <i class="bi bi-clipboard"></i>
                            </button>`;
                    } else if (coordsStr) {
                        copyButtonHtml = `
                            <button class="btn btn-sm btn-outline-secondary geolocation-copy-btn" 
                                    onclick="event.stopPropagation(); copyGeolocationCoordinates('${safeCoords}', this);"
                                    title="${translations.copyCoordinates || 'Copy coordinates'}"
                                    aria-label="${translations.copyCoordinates || 'Copy coordinates'}">
                                <i class="bi bi-clipboard"></i>
                            </button>`;
                    }
                }
            }
            
            html += `
                <div class="file-row-item" 
                     data-section="${section}" 
                     data-item-id="${itemId}" 
                     data-item-name="${safeDisplayName}"
                     ${item.is_group ? 'data-is-group="true"' : ''}
                     ${groupDataAttr}
                     role="button"
                     tabindex="0"
                     title="${sectionLabel}: ${escapeHtml(displayName)}"
                     aria-label="${sectionLabel}: ${escapeHtml(displayName)}">
                    ${copyButtonHtml}
                    <div class="file-row-info">
                        <div class="file-row-icon"><i class="bi bi-${getSectionIcon(section)}" aria-hidden="true"></i></div>
                        <div class="file-row-details">
                            <div class="file-row-name" contenteditable="false" data-editable="true" data-item-id="${itemId}" data-section="${section}" data-field="name" onblur="saveItemField?.(this)" ondblclick="enableItemEdit?.(this)">
                                ${escapeHtml(displayName)}${groupIndicator}
                            </div>
                            <div class="file-row-meta" contenteditable="false" data-editable="true" data-item-id="${itemId}" data-section="${section}" data-field="details" onblur="saveItemField?.(this)" ondblclick="enableItemEdit?.(this)">${escapeHtml(details)}</div>
                            ${item.is_group && item.similar_titles ? `
                                <div class="similar-titles-preview">
                                    <i class="bi bi-arrow-down-circle similar-titles-toggle" onclick="toggleSimilarTitles?.(this, ${item.group_id})"></i>
                                    <span>${item.group_count} ${item.is_identical ? 'identical' : 'similar'} titles</span>
                                    <div class="similar-titles-list" id="similar-titles-${item.group_id}" hidden>
                                        ${item.similar_titles.map(st => `
                                            <div class="similar-title-row">
                                                <span class="badge bg-secondary">${st.file_count || 0}</span>
                                                ${escapeHtml(st.name || 'Unknown')}
                                            </div>
                                        `).join('')}
                                    </div>
                                </div>
                            ` : ''}
                        </div>
                    </div>
                </div>
            `;
        });
    }

    html += '</div>'; // list view
    if (showPagination) {
        html += renderSectionPaginationControls(section);
    }
    html += '</div>'; // section
    return html;
}

