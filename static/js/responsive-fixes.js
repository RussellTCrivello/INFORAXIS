/**
 * Responsive data hygiene for INFORAXIS.
 *
 * The enterprise workspace layout is owned by CSS (styles.css,
 * responsive-fixes.css, and data-interface.css). This module deliberately avoids
 * writing visual/layout inline styles; its only job is to add semantic metadata
 * that CSS and assistive technology can use on compact screens.
 */

(function() {
    'use strict';

    const TABLE_SELECTOR = 'table';
    const CELL_SELECTOR = 'tbody tr:not(.ia-detail-row) td';

    function headerText(headers, index) {
        const header = headers[index];
        if (!header) return '';
        return (header.textContent || '')
            .replace(/\s+/g, ' ')
            .trim();
    }

    function tablesFromRoot(root) {
        const tables = [];
        const elementRoot = root instanceof Element ? root : null;
        const closestTable = elementRoot?.closest(TABLE_SELECTOR);

        if (elementRoot?.matches(TABLE_SELECTOR)) tables.push(elementRoot);
        if (closestTable) tables.push(closestTable);
        root.querySelectorAll?.(TABLE_SELECTOR).forEach((table) => tables.push(table));

        return Array.from(new Set(tables));
    }

    /**
     * Add data-label attributes to cells so narrow layouts can expose column
     * context without JavaScript taking over the table layout.
     */
    function annotateResponsiveTables(root = document) {
        tablesFromRoot(root).forEach((table) => {
            if (table.dataset.responsiveLabels === 'false') return;

            const headers = Array.from(table.querySelectorAll('thead th'));
            if (!headers.length) return;

            table.querySelectorAll(CELL_SELECTOR).forEach((cell) => {
                if (cell.hasAttribute('data-label')) return;
                const index = cell.cellIndex;
                const label = headerText(headers, index);
                if (label) cell.setAttribute('data-label', label);
            });
        });
    }

    function initResponsiveMetadata() {
        annotateResponsiveTables(document);

        const observer = new MutationObserver((mutations) => {
            mutations.forEach((mutation) => {
                mutation.addedNodes.forEach((node) => {
                    if (node.nodeType === Node.ELEMENT_NODE) {
                        annotateResponsiveTables(node);
                    }
                });
            });
        });

        observer.observe(document.documentElement, {
            childList: true,
            subtree: true
        });

        window.INFORAXISResponsive = Object.assign(window.INFORAXISResponsive || {}, {
            annotateResponsiveTables
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initResponsiveMetadata);
    } else {
        initResponsiveMetadata();
    }
})();
