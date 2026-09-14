/**
 * Files List Page JavaScript
 * Extracted from file/files_list.html
 */

import FileManagement from '../modules/file-operations/file-management.js';

// Load translations from JSON script tag
let translations = {};

document.addEventListener('DOMContentLoaded', function() {
    // Load translations from JSON script tag
    const pageDataEl = document.getElementById('files-list-page-data');
    if (pageDataEl) {
        try {
            const data = JSON.parse(pageDataEl.textContent);
            translations = data.translations || {};
            // Make translations available globally for FileManagement
            window.translations = window.translations || {};
            Object.assign(window.translations, translations);
        } catch (e) {
            console.error('Error parsing files list page data:', e);
        }
    }
    
    // Load page data (pagination info) from JSON script tag
    const pageInfoEl = document.getElementById('page-data');
    if (pageInfoEl) {
        try {
            const pageData = JSON.parse(pageInfoEl.textContent);
            // Set data for FileManagement
            window.fileManagementData = pageData;
            FileManagement.data = pageData;
            console.log('Page data loaded:', pageData);
        } catch (e) {
            console.error('Error parsing page data:', e);
        }
    }
    
    // Initialize file management
    if (FileManagement && typeof FileManagement.init === 'function') {
        FileManagement.init();
    }
    
    console.log('Files list page loaded');
});

// Expose functions to window for onclick handlers
window.selectAllFiles = function() {
    if (FileManagement && typeof FileManagement.selectAllFiles === 'function') {
        FileManagement.selectAllFiles();
    }
};

window.deselectAllFiles = function() {
    if (FileManagement && typeof FileManagement.deselectAllFiles === 'function') {
        FileManagement.deselectAllFiles();
    }
};

window.toggleSelectAll = function(checkbox) {
    if (FileManagement && typeof FileManagement.toggleSelectAll === 'function') {
        FileManagement.toggleSelectAll(checkbox);
    }
};

window.updateBulkToolbar = function() {
    if (FileManagement && typeof FileManagement.updateBulkToolbar === 'function') {
        FileManagement.updateBulkToolbar();
    }
};

window.bulkAnalyze = function() {
    if (FileManagement && typeof FileManagement.bulkAnalyze === 'function') {
        FileManagement.bulkAnalyze();
    }
};

window.bulkExport = function() {
    if (FileManagement && typeof FileManagement.bulkExport === 'function') {
        FileManagement.bulkExport();
    }
};

window.clearFileSearch = function() {
    if (FileManagement && typeof FileManagement.clearFileSearch === 'function') {
        FileManagement.clearFileSearch();
    }
};

window.changeFilesPageSize = function() {
    if (FileManagement && typeof FileManagement.changeFilesPageSize === 'function') {
        FileManagement.changeFilesPageSize();
    }
};
