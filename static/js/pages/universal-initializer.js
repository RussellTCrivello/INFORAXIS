/**
 * Universal Page Initializer
 * Automatically detects page type and initializes appropriate handlers
 * NO INLINE JAVASCRIPT NEEDED - Everything is external!
 */

import { initBasePage } from './base-page-handler.js';
import { getPageData } from './data-helper.js';

// Page type detection patterns
const pageDetectors = [
    // Specific page types (checked first)
    { selector: '[data-page-type]', getType: (el) => el.dataset.pageType },
    { selector: 'body[data-page-type]', getType: (el) => el.dataset.pageType },
    
    // Route-based detection (fallback)
    { selector: 'body', getType: (el) => {
        const path = window.location.pathname;
        const endpoint = el.dataset.currentEndpoint || '';
        
        // Map routes to page types
        if (path.includes('/files') && !path.match(/\/file\/\d+/)) return 'files-list';
        if (path.match(/\/file\/\d+/)) return 'file-detail';
        if (path.match(/\/keywords\/\d+/)) return 'keyword-detail';
        if (path.includes('/keywords')) return 'keywords-list';
        if (path.match(/\/categories\/\d+\/words/)) return 'category-words';  // Must be before general /words check
        if (path.match(/\/words\/\d+/)) return 'word-detail';
        if (path.includes('/words')) return 'words-list';
        if (path.match(/\/sources\/\d+\/categories-keywords/)) return 'source-categories-keywords';
        if (path.match(/\/sources\/\d+/)) return 'source-detail';
        if (path.includes('/sources')) return 'sources-list';
        if (path.match(/\/sides\/\d+\/categories-keywords/)) return 'side-categories-keywords';
        if (path.match(/\/sides\/\d+/)) return 'side-detail';
        if (path.includes('/sides')) return 'sides-list';
        if (path === '/search/enhanced') return 'search-enhanced';
        if (path === '/search/advanced') return 'search-advanced';
        if (path.includes('/search/saved')) return 'saved-searches';
        if (path === '/search') return 'search';
        if (path === '/upload') return 'upload';
        if (path === '/' || path === '/dashboard') return 'dashboard';
        if (path.includes('/dashboard/comprehensive')) return 'comprehensive-dashboard';
        if (path.includes('/notifications')) return 'notifications';
        if (path.includes('/import') || path.includes('/export')) return 'import-export';
        if (path.includes('/analysis/batch')) return 'analysis-batch';
        if (path.includes('/email-words')) return 'email-words';
        if (path.includes('/archives')) return 'archives';
        if (path.includes('/analytics/path-analysis') || path.includes('/analysis/path')) return 'path-analysis';
        
        return 'default';
    }}
];

// Page handler registry
const pageHandlers = {
    'files-list': () => import('./files-list-page.js'),
    'file-detail': () => import('./file-detail-page.js'),
    'keywords-list': () => import('./keywords-list-page.js'),
    'keyword-detail': () => import('./keyword-detail-page.js'),
    'category-words': () => import('./category-words-page.js'),
    'words-list': () => import('./words-list-page.js'),
    'word-detail': () => import('./word-detail-page.js'),
    'sources-list': () => import('./sources-list-page.js'),
    'source-detail': () => import('./source-detail-page.js'),
    'source-categories-keywords': () => import('./source-categories-keywords-page.js'),
    'sides-list': () => import('./sides-list-page.js'),
    'side-detail': () => import('./side-detail-page.js'),
    'side-categories-keywords': () => import('./side-categories-keywords-page.js'),
    'search': () => import('./search-page.js'),
    'search-enhanced': () => import('./search-enhanced-page.js'),
    'search-advanced': () => import('./search-advanced-page.js'),
    'saved-searches': () => import('./saved-searches-page.js'),
    'upload': () => import('./upload-page.js'),
    'dashboard': () => import('./dashboard-page.js'),
    'comprehensive-dashboard': () => import('./comprehensive-dashboard-page.js'),
    'notifications': () => import('./notifications-page.js'),
    'import-export': () => import('./import-export-page.js'),
    'analysis-batch': () => import('./analysis-batch-page.js'),
    'email-words': () => import('./email-words-page.js'),
    'archives': () => import('./archives-page.js'),
    'path-analysis': () => import('./path-analysis-page.js'),
    'concurrency-workspace': () => import('./concurrency-dashboard-page.js'),
    'import-workspace': () => import('./import-center-page.js'),
    'users-workspace': () => import('./users-page.js'),
    'default': () => Promise.resolve({ default: () => {} }) // No-op for default
};

const pageScriptFiles = {
    'files-list': 'files-list-page.js',
    'file-detail': 'file-detail-page.js',
    'keywords-list': 'keywords-list-page.js',
    'keyword-detail': 'keyword-detail-page.js',
    'category-words': 'category-words-page.js',
    'words-list': 'words-list-page.js',
    'word-detail': 'word-detail-page.js',
    'sources-list': 'sources-list-page.js',
    'source-detail': 'source-detail-page.js',
    'source-categories-keywords': 'source-categories-keywords-page.js',
    'sides-list': 'sides-list-page.js',
    'side-detail': 'side-detail-page.js',
    'side-categories-keywords': 'side-categories-keywords-page.js',
    'search': 'search-page.js',
    'search-enhanced': 'search-enhanced-page.js',
    'search-advanced': 'search-advanced-page.js',
    'saved-searches': 'saved-searches-page.js',
    'upload': 'upload-page.js',
    'dashboard': 'dashboard-page.js',
    'comprehensive-dashboard': 'comprehensive-dashboard-page.js',
    'notifications': 'notifications-page.js',
    'import-export': 'import-export-page.js',
    'analysis-batch': 'analysis-batch-page.js',
    'email-words': 'email-words-page.js',
    'archives': 'archives-page.js',
    'path-analysis': 'path-analysis-page.js',
    'concurrency-workspace': 'concurrency-dashboard-page.js',
    'import-workspace': 'import-center-page.js',
    'users-workspace': 'users-page.js'
};

/**
 * Detect page type
 */
function detectPageType() {
    for (const detector of pageDetectors) {
        const element = document.querySelector(detector.selector);
        if (element) {
            const pageType = detector.getType(element);
            if (pageType && pageType !== 'default') {
                return pageType;
            }
        }
    }
    return 'default';
}

function hasExplicitPageModule(pageType) {
    const scriptFile = pageScriptFiles[pageType];
    if (!scriptFile) return false;

    return Array.from(document.scripts).some((script) => {
        const src = script.getAttribute('src') || '';
        return src.includes(`/js/pages/${scriptFile}`) || src.includes(`/static/js/pages/${scriptFile}`);
    });
}

function hasBasePageScript() {
    return Array.from(document.scripts).some((script) => {
        const src = script.getAttribute('src') || '';
        return src.includes('/js/pages/base-page.js') || src.includes('/static/js/pages/base-page.js');
    });
}

/**
 * Initialize page
 */
export async function initializePage() {
    // base-page.js is already loaded by base.html. Only use the lightweight
    // fallback handler on pages that include the universal initializer without
    // the global base script to avoid duplicate menu listeners and intervals.
    if (!hasBasePageScript()) {
        initBasePage();
    }
    
    // Detect page type
    const pageType = detectPageType();
    
    if (pageType === 'default') {
        // No specific handler needed
        return;
    }
    
    // If the template already included this page module, let that module's own
    // DOMContentLoaded hooks run and avoid a second dynamic init/warning pass.
    if (hasExplicitPageModule(pageType)) {
        return;
    }

    // Get page handler
    const handler = pageHandlers[pageType];
    if (!handler) {
        console.warn(`No handler found for page type: ${pageType}`);
        return;
    }
    
    try {
        // Load and initialize page-specific module
        const pageModule = await handler();
        if (pageModule && pageModule.default && typeof pageModule.default === 'function') {
            await pageModule.default();
        } else if (pageModule && typeof pageModule.init === 'function') {
            await pageModule.init();
        } else {
            console.warn(`Page module for ${pageType} does not export a default init function`);
        }
    } catch (error) {
        console.error(`Error initializing page ${pageType}:`, error);
    }
}

// Auto-initialize when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initializePage);
} else {
    initializePage();
}

// Export for manual initialization if needed
export default { initializePage, detectPageType };

