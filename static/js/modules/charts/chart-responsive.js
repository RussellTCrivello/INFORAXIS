/**
 * Chart Responsiveness Helper
 * Keeps Chart.js charts responsive without wrapping the Chart constructor or
 * writing layout dimensions inline. Page-level CSS owns chart height; this
 * helper only applies safe defaults, registers one resize listener, and offers
 * utilities for dynamically-created charts.
 */

(function() {
    'use strict';

    const state = window.__InforaxisChartResponsiveState || {
        bootstrapped: false,
        resizeHandlerAttached: false,
        delayedInitScheduled: false,
        resizeTimeout: null
    };
    window.__InforaxisChartResponsiveState = state;

    const defaultResponsiveConfig = {
        responsive: true,
        maintainAspectRatio: false,
        resizeDelay: 120,
        plugins: {
            legend: {
                labels: {
                    boxWidth: 12,
                    padding: 8,
                    font: {
                        size: 11
                    }
                }
            },
            tooltip: {
                padding: 8,
                titleFont: {
                    size: 12
                },
                bodyFont: {
                    size: 11
                },
                footerFont: {
                    size: 10
                }
            }
        }
    };

    const mobileChartConfig = {
        plugins: {
            legend: {
                position: 'bottom',
                labels: {
                    boxWidth: 10,
                    padding: 6,
                    font: {
                        size: 10
                    }
                }
            },
            tooltip: {
                padding: 6,
                titleFont: {
                    size: 11
                },
                bodyFont: {
                    size: 10
                }
            }
        },
        scales: {
            x: {
                ticks: {
                    font: {
                        size: 10
                    },
                    maxRotation: 45,
                    minRotation: 0
                }
            },
            y: {
                ticks: {
                    font: {
                        size: 10
                    }
                }
            }
        }
    };

    function mergeDefaults(target = {}, source = {}) {
        Object.entries(source).forEach(([key, value]) => {
            if (target[key] === false || target[key] === null) return;
            if (value && typeof value === 'object' && !Array.isArray(value)) {
                target[key] = mergeDefaults(target[key] || {}, value);
            } else if (target[key] === undefined) {
                target[key] = value;
            }
        });
        return target;
    }

    function isMobileViewport() {
        return window.innerWidth <= 768;
    }

    function chartEntries() {
        if (typeof Chart === 'undefined') return [];

        if (Chart.instances instanceof Map) {
            return Array.from(Chart.instances.values()).filter(Boolean);
        }

        if (Chart.instances && typeof Chart.instances === 'object') {
            return Object.values(Chart.instances).filter(Boolean);
        }

        return Array.from(document.querySelectorAll('canvas')).map((canvas) => {
            try {
                return typeof Chart.getChart === 'function' ? Chart.getChart(canvas) : null;
            } catch (error) {
                return null;
            }
        }).filter(Boolean);
    }

    /**
     * Apply responsive configuration to a chart.
     */
    function applyResponsiveConfig(chart, isMobile = isMobileViewport()) {
        if (!chart || !chart.options) return;

        mergeDefaults(chart.options, defaultResponsiveConfig);

        if (isMobile) {
            mergeDefaults(chart.options, mobileChartConfig);
        }

        chart.options.responsive = true;
        chart.options.maintainAspectRatio = false;
        chart.options.resizeDelay = Math.max(Number(chart.options.resizeDelay) || 0, defaultResponsiveConfig.resizeDelay);

        if (typeof chart.update === 'function') {
            chart.update('none');
        }
    }

    /**
     * Mark a chart container as responsive without overriding its height.
     */
    function makeChartContainerResponsive(container) {
        if (!container || !(container instanceof HTMLElement)) return;

        const canvas = container.matches('canvas') ? container : container.querySelector('canvas');
        if (!canvas) return;

        const targetContainer = canvas === container ? canvas.parentElement : container;
        if (!targetContainer || !(targetContainer instanceof HTMLElement)) return;

        if (!targetContainer.classList.contains('chart-container') && !targetContainer.classList.contains('chart-container-layout')) {
            targetContainer.classList.add('chart-container');
        }

        targetContainer.classList.add('ia-chart-responsive');
        canvas.classList.add('ia-chart-canvas');
    }

    function applyChartDefaults() {
        if (typeof Chart === 'undefined' || !Chart.defaults) return;

        Chart.defaults.responsive = true;
        Chart.defaults.maintainAspectRatio = false;
        Chart.defaults.resizeDelay = Math.max(Number(Chart.defaults.resizeDelay) || 0, defaultResponsiveConfig.resizeDelay);
    }

    /**
     * Initialize responsive behavior for all charts.
     */
    function initChartResponsiveness(root = document) {
        if (typeof Chart === 'undefined') {
            return;
        }

        applyChartDefaults();

        const chartContainers = root.querySelectorAll?.('.chart-container, .chart-container-layout, .chart-card, .dashboard-chart, canvas') || [];
        chartContainers.forEach((container) => {
            if (container instanceof HTMLElement) {
                makeChartContainerResponsive(container);
            }
        });

        chartEntries().forEach((chart) => {
            makeChartContainerResponsive(chart.canvas?.parentElement || chart.canvas);
            applyResponsiveConfig(chart, isMobileViewport());
        });
    }

    function handleResize() {
        window.clearTimeout(state.resizeTimeout);
        state.resizeTimeout = window.setTimeout(() => {
            initChartResponsiveness(document);
            chartEntries().forEach((chart) => {
                if (chart && typeof chart.resize === 'function') {
                    chart.resize();
                }
            });
        }, 180);
    }

    function scheduleDelayedInit() {
        if (state.delayedInitScheduled) return;
        state.delayedInitScheduled = true;
        window.setTimeout(() => initChartResponsiveness(document), 500);
    }

    function init() {
        if (state.bootstrapped) {
            initChartResponsiveness(document);
            return;
        }

        state.bootstrapped = true;
        initChartResponsiveness(document);

        if (!state.resizeHandlerAttached) {
            window.addEventListener('resize', handleResize, { passive: true });
            window.addEventListener('orientationchange', () => window.setTimeout(handleResize, 200), { passive: true });
            state.resizeHandlerAttached = true;
        }

        scheduleDelayedInit();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init, { once: true });
    } else {
        init();
    }

    const api = {
        applyConfig: applyResponsiveConfig,
        makeContainerResponsive: makeChartContainerResponsive,
        init: initChartResponsiveness,
        defaultConfig: defaultResponsiveConfig,
        mobileConfig: mobileChartConfig
    };

    window.__InforaxisChartResponsiveApi = api;
    window.ChartResponsive = api;
})();

const ChartResponsiveModule = {
    get applyConfig() { return window.__InforaxisChartResponsiveApi?.applyConfig; },
    get makeContainerResponsive() { return window.__InforaxisChartResponsiveApi?.makeContainerResponsive; },
    get init() { return window.__InforaxisChartResponsiveApi?.init; },
    get defaultConfig() { return window.__InforaxisChartResponsiveApi?.defaultConfig; },
    get mobileConfig() { return window.__InforaxisChartResponsiveApi?.mobileConfig; }
};

export default ChartResponsiveModule;
