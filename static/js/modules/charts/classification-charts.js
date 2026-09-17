/**
 * Classification Charts
 * Extracted from legacy file-management-system.js
 */

import { translations } from '../core/config.js';
import { escapeHtml } from '../core/utils.js';

// Chart state management
const classificationChartState = {
    currentChart: null,
    currentDataType: 'categories', // 'categories', 'words', 'keywords'
    currentChartType: 'pie', // 'pie', 'bar', 'doughnut', 'line'
    chartData: null,
    filterValue: ''
};

// Color palette for charts
const chartColors = [
    '#667eea', '#764ba2', '#10b981', '#f59e0b', '#ef4444',
    '#06b6d4', '#8b5cf6', '#ec4899', '#f97316', '#14b8a6',
    '#6366f1', '#84cc16', '#f43f5e', '#06b6d4', '#a855f7',
    '#3b82f6', '#8b5cf6', '#ec4899', '#f97316', '#14b8a6'
];

/**
 * Load classification chart data and render
 */
export function loadClassificationCharts(fileId) {
    const analysisSection = document.getElementById('fileAnalysisSection');
    if (!analysisSection) return;
    
    // Show loading state using the shared analytical panel classes. Controls
    // remain fixed while the chart and backing data table use their own bounded
    // scroll regions.
    analysisSection.innerHTML = `
        <div class="classification-charts-container">
            <div class="classification-charts-controls ia-fixed-control-surface" data-ia-role="controls">
                <div class="data-type-tabs" role="tablist" aria-label="${translations.analysis || 'Analysis'}">
                    <button type="button" class="data-type-tab active" data-type="categories" onclick="switchDataType('categories')">
                        <i class="bi bi-tags" aria-hidden="true"></i> ${translations.categories || 'Categories'}
                    </button>
                    <button type="button" class="data-type-tab" data-type="words" onclick="switchDataType('words')">
                        <i class="bi bi-file-text" aria-hidden="true"></i> ${translations.words || 'Words'}
                    </button>
                    <button type="button" class="data-type-tab" data-type="keywords" onclick="switchDataType('keywords')">
                        <i class="bi bi-key" aria-hidden="true"></i> ${translations.keywords || 'Keywords'}
                    </button>
                </div>
                <div class="chart-filter-container">
                    <label class="visually-hidden" for="chartFilterInput">${translations.filterData || 'Filter data'}</label>
                    <input type="text" id="chartFilterInput" class="form-control form-control-sm"
                           placeholder="${translations.filterData || 'Filter...'}"
                           oninput="filterChartData(this.value)">
                </div>
            </div>
            <div class="chart-and-table-container">
                <div class="chart-container classification-chart-panel">
                    <canvas id="classificationChart"></canvas>
                </div>
                <div class="chart-data-table-container ia-data-scroll-region" data-ia-scroll="true">
                    <div id="chartDataTable" class="chart-data-table">
                        <div class="chart-data-table-title">
                            ${translations.dataTable || 'Data Table'}
                        </div>
                        <div class="table-loading chart-table-state">
                            ${translations.loadingAnalysis || 'Loading...'}
                        </div>
                    </div>
                </div>
            </div>
            <div class="chart-loading chart-state">
                ${translations.loadingAnalysis || 'Loading analysis...'}
            </div>
        </div>
    `;
    
    // Fetch chart data
    fetch(`/file/${fileId}/chart-data`)
        .then(response => {
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            return response.json();
        })
        .then(result => {
            if (!result.success || !result.data) {
                throw new Error(result.error || 'Failed to load chart data');
            }
            
            classificationChartState.chartData = result.data;
            renderClassificationChart();
            renderChartDataTable();
            renderDuplicateWords();
        })
        .catch(error => {
            console.error('Error loading classification charts:', error);
            const chartContainer = analysisSection.querySelector('.chart-container');
            if (chartContainer) {
                chartContainer.innerHTML = `<div class="empty-state chart-state chart-state-error">
                    ${translations.errorLoadingAnalysis || 'Error loading analysis'}: ${escapeHtml(error.message)}
                </div>`;
            }
        });
}

/**
 * Switch between data types (categories, words, keywords)
 */
export function switchDataType(dataType) {
    classificationChartState.currentDataType = dataType;
    classificationChartState.filterValue = '';
    
    // Update active tab
    document.querySelectorAll('.data-type-tab').forEach(tab => {
        tab.classList.remove('active');
        if (tab.getAttribute('data-type') === dataType) {
            tab.classList.add('active');
        }
    });
    
    // Clear filter
    const filterInput = document.getElementById('chartFilterInput');
    if (filterInput) {
        filterInput.value = '';
    }
    
    renderClassificationChart();
    renderChartDataTable();
}

/**
 * Switch between chart types (pie, bar, doughnut, line)
 */
export function switchChartType(chartType) {
    classificationChartState.currentChartType = chartType;
    renderClassificationChart();
}

/**
 * Filter chart data
 */
export function filterChartData(filterValue) {
    classificationChartState.filterValue = filterValue.toLowerCase().trim();
    renderClassificationChart();
    renderChartDataTable();
}

/**
 * Render the classification chart
 */
export function renderClassificationChart() {
    if (!classificationChartState.chartData) {
        return;
    }
    
    const canvas = document.getElementById('classificationChart');
    if (!canvas) {
        return;
    }
    
    // Get data based on current data type
    let rawData = [];
    switch (classificationChartState.currentDataType) {
        case 'categories':
            rawData = classificationChartState.chartData.categories || [];
            break;
        case 'words':
            rawData = classificationChartState.chartData.words || [];
            break;
        case 'keywords':
            rawData = classificationChartState.chartData.keywords || [];
            break;
    }
    
    // Apply filter
    let filteredData = rawData;
    if (classificationChartState.filterValue) {
        filteredData = rawData.filter(item => 
            item.name && item.name.toLowerCase().includes(classificationChartState.filterValue)
        );
    }
    
    // Limit to top 20 items for better visualization
    filteredData = filteredData.slice(0, 20);
    
    // Check if we have data
    if (!filteredData || filteredData.length === 0) {
        const ctx = canvas.getContext('2d');
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        
        // Show empty state
        const container = canvas.parentElement;
        if (container) {
            const emptyDiv = document.createElement('div');
            emptyDiv.className = 'empty-state chart-state';
            emptyDiv.textContent = translations.noCategoriesAssigned || 'No data available';
            
            // Remove existing empty state if any
            const existingEmpty = container.querySelector('.empty-state');
            if (existingEmpty) {
                existingEmpty.remove();
            }
            container.appendChild(emptyDiv);
        }
        
        // Destroy existing chart - check both our state and Chart.js registry
        if (classificationChartState.currentChart) {
            try {
                classificationChartState.currentChart.destroy();
            } catch (e) {
                console.warn('Error destroying chart from state:', e);
            }
            classificationChartState.currentChart = null;
        }
        
        // Also check if Chart.js has a chart registered on this canvas
        if (typeof Chart !== 'undefined' && Chart.getChart) {
            const existingChart = Chart.getChart(canvas);
            if (existingChart) {
                try {
                    existingChart.destroy();
                } catch (e) {
                    console.warn('Error destroying chart from Chart.js registry:', e);
                }
            }
        }
        
        return;
    }
    
    // Remove empty state if exists
    const container = canvas.parentElement;
    if (container) {
        const emptyState = container.querySelector('.empty-state');
        if (emptyState) {
            emptyState.remove();
        }
    }
    
    // Prepare chart data
    const labels = filteredData.map(item => {
        const name = item.name || 'Unknown';
        return name.length > 30 ? name.substring(0, 27) + '...' : name;
    });
    
    const dataValues = filteredData.map(item => item.count || 0);
    const fullLabels = filteredData.map(item => item.name || 'Unknown');
    
    // Generate colors
    const colors = chartColors.slice(0, filteredData.length);
    
    // Destroy existing chart - check both our state and Chart.js registry
    if (classificationChartState.currentChart) {
        try {
            classificationChartState.currentChart.destroy();
        } catch (e) {
            console.warn('Error destroying chart from state:', e);
        }
        classificationChartState.currentChart = null;
    }
    
    // Also check if Chart.js has a chart registered on this canvas
    if (typeof Chart !== 'undefined' && Chart.getChart) {
        const existingChart = Chart.getChart(canvas);
        if (existingChart) {
            try {
                existingChart.destroy();
            } catch (e) {
                console.warn('Error destroying chart from Chart.js registry:', e);
            }
        }
    }
    
    // Clear the canvas
    const ctx = canvas.getContext('2d');
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    const chartType = classificationChartState.currentChartType;
    
    const chartConfig = {
        type: chartType,
        data: {
            labels: labels,
            datasets: [{
                label: classificationChartState.currentDataType.charAt(0).toUpperCase() + 
                       classificationChartState.currentDataType.slice(1),
                data: dataValues,
                backgroundColor: chartType === 'line' ? chartColors[0] : colors,
                borderColor: chartType === 'line' ? chartColors[0] : colors.map(c => c + '80'),
                borderWidth: chartType === 'line' ? 2 : 1
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    display: chartType !== 'bar' && chartType !== 'line',
                    position: 'right',
                    labels: {
                        boxWidth: 12,
                        padding: 8,
                        font: {
                            size: 11
                        }
                    }
                },
                tooltip: {
                    callbacks: {
                        label: function(context) {
                            const index = context.dataIndex;
                            const fullLabel = fullLabels[index];
                            const value = context.parsed.y || context.parsed;
                            const percentage = classificationChartState.currentDataType === 'categories' && 
                                filteredData[index].percentage ? 
                                ` (${filteredData[index].percentage.toFixed(1)}%)` : '';
                            return `${fullLabel}: ${value}${percentage}`;
                        }
                    }
                },
                title: {
                    display: false
                }
            },
            scales: (chartType === 'bar' || chartType === 'line') ? {
                y: {
                    beginAtZero: true,
                    ticks: {
                        font: {
                            size: 11
                        }
                    }
                },
                x: {
                    ticks: {
                        font: {
                            size: 10
                        },
                        maxRotation: 45,
                        minRotation: 45
                    }
                }
            } : {}
        }
    };
    
    // Special handling for horizontal bar chart
    if (chartType === 'bar' && filteredData.length > 10) {
        chartConfig.options.indexAxis = 'y';
        chartConfig.options.scales = {
            x: {
                beginAtZero: true,
                ticks: {
                    font: {
                        size: 11
                    }
                }
            },
            y: {
                ticks: {
                    font: {
                        size: 10
                    }
                }
            }
        };
    }
    
    // Require Chart global
    if (typeof Chart === 'undefined') {
        console.error('Chart.js not loaded. Please include chart.js before using classification charts.');
        return;
    }
    
    // Double-check that no chart exists on the canvas before creating new one
    // This prevents "Canvas is already in use" errors
    if (Chart.getChart) {
        const existingChart = Chart.getChart(canvas);
        if (existingChart && existingChart !== classificationChartState.currentChart) {
            try {
                existingChart.destroy();
            } catch (e) {
                console.warn('Error destroying existing chart before creating new one:', e);
            }
        }
    }
    
    // Create new chart
    try {
        classificationChartState.currentChart = new Chart(ctx, chartConfig);
    } catch (error) {
        console.error('Error creating chart:', error);
        // If creation fails, try once more after clearing and destroying any remaining chart
        if (Chart.getChart) {
            const existingChart = Chart.getChart(canvas);
            if (existingChart) {
                try {
                    existingChart.destroy();
                } catch (e) {
                    // Ignore errors during cleanup
                }
            }
        }
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        // Wait a tiny bit for Chart.js to clean up
        setTimeout(() => {
            try {
                classificationChartState.currentChart = new Chart(ctx, chartConfig);
                // Force update after creation
                if (classificationChartState.currentChart) {
                    classificationChartState.currentChart.update('none');
                }
            } catch (retryError) {
                console.error('Error creating chart on retry:', retryError);
            }
        }, 50);
        return; // Early return if we're retrying
    }
    
    // Force update to ensure chart is fully initialized
    setTimeout(() => {
        if (classificationChartState.currentChart) {
            classificationChartState.currentChart.update('none');
        }
    }, 50);
    
    // Attach export buttons - wait for ChartExport to be available with retry logic
    function attachClassificationControls() {
        if (window.ChartExport && window.ChartExport.attachExportButtonsToCharts) {
            setTimeout(() => {
                let chartContainer = canvas.closest('.classification-charts-container');
                if (!chartContainer) {
                    chartContainer = canvas.closest('.file-details-analysis-section, #fileAnalysisSection');
                }
                if (!chartContainer) {
                    chartContainer = canvas.closest('.chart-and-table-container');
                }
                if (!chartContainer) {
                    chartContainer = canvas.closest('.chart-container');
                }
                if (!chartContainer) {
                    let parent = canvas.parentElement;
                    let attempts = 0;
                    while (parent && attempts < 5) {
                        if (parent.classList && (parent.classList.contains('classification-charts-container') ||
                             parent.id === 'fileAnalysisSection' ||
                             parent.classList.contains('file-details-analysis-section'))) {
                            chartContainer = parent;
                            break;
                        }
                        parent = parent.parentElement;
                        attempts++;
                    }
                }
                
                if (chartContainer) {
                    window.ChartExport.attachExportButtonsToCharts(chartContainer);
                } else {
                    const fileAnalysisSection = document.getElementById('fileAnalysisSection');
                    if (fileAnalysisSection) {
                        window.ChartExport.attachExportButtonsToCharts(fileAnalysisSection);
                    } else if (canvas.parentElement) {
                        window.ChartExport.attachExportButtonsToCharts(canvas.parentElement);
                    }
                }
            }, 200);
        } else {
            setTimeout(attachClassificationControls, 200);
        }
    }
    setTimeout(attachClassificationControls, 150);
    
    // Hide loading indicator
    const loadingDiv = document.querySelector('.chart-loading');
    if (loadingDiv) {
        loadingDiv.hidden = true;
    }
}

/**
 * Render the data table next to the chart
 */
export function renderChartDataTable() {
    if (!classificationChartState.chartData) {
        return;
    }
    
    const tableContainer = document.getElementById('chartDataTable');
    if (!tableContainer) {
        return;
    }
    
    // Get data based on current data type
    let rawData = [];
    switch (classificationChartState.currentDataType) {
        case 'categories':
            rawData = classificationChartState.chartData.categories || [];
            break;
        case 'words':
            rawData = classificationChartState.chartData.words || [];
            break;
        case 'keywords':
            rawData = classificationChartState.chartData.keywords || [];
            break;
    }
    
    // Apply filter
    let filteredData = rawData;
    if (classificationChartState.filterValue) {
        filteredData = rawData.filter(item => 
            item.name && item.name.toLowerCase().includes(classificationChartState.filterValue)
        );
    }
    
    // Limit to top 20 items
    filteredData = filteredData.slice(0, 20);
    
    // Remove loading indicator
    const loadingDiv = tableContainer.querySelector('.table-loading');
    if (loadingDiv) {
        loadingDiv.remove();
    }
    
    const currentLabel = classificationChartState.currentDataType === 'categories'
        ? (translations.category || 'Category')
        : classificationChartState.currentDataType === 'words'
            ? (translations.word || 'Word')
            : (translations.keyword || 'Keyword');

    if (!filteredData || filteredData.length === 0) {
        tableContainer.innerHTML = `
            <div class="chart-data-table-title">${translations.dataTable || 'Data Table'}</div>
            <div class="chart-table-state">${translations.noDataAvailable || 'No data available'}</div>
        `;
        return;
    }
    
    let tableHtml = `
        <div class="chart-data-table-title">${translations.dataTable || 'Data Table'} (${filteredData.length})</div>
        <table class="chart-data-table-grid">
            <thead>
                <tr>
                    <th>${currentLabel}</th>
                    <th class="text-end">${translations.count || 'Count'}</th>
                    ${classificationChartState.currentDataType === 'categories' ? `<th class="text-end">${translations.percentage || '%'}</th>` : ''}
                </tr>
            </thead>
            <tbody>
    `;
    
    filteredData.forEach((item) => {
        tableHtml += `
            <tr>
                <td class="chart-data-name" title="${escapeHtml(item.name || 'Unknown')}">
                    ${escapeHtml(item.name || 'Unknown')}
                </td>
                <td class="text-end chart-data-count">${(item.count || 0).toLocaleString()}</td>
                ${classificationChartState.currentDataType === 'categories' ? `
                    <td class="text-end chart-data-percent">${item.percentage ? item.percentage.toFixed(1) + '%' : '-'}</td>
                ` : ''}
            </tr>
        `;
    });
    
    tableHtml += `</tbody></table>`;
    tableContainer.innerHTML = tableHtml;
}

/**
 * Render duplicate words section
 */
export function renderDuplicateWords() {
    if (!classificationChartState.chartData) {
        return;
    }
    
    const container = document.getElementById('duplicateWordsContainer');
    const countSpan = document.getElementById('duplicateWordsCount');
    if (!container) {
        return;
    }
    
    const repeatedElements = classificationChartState.chartData.repeated_elements || [];
    
    if (countSpan) {
        countSpan.textContent = `(${repeatedElements.length})`;
    }
    
    const loadingDiv = container.querySelector('.duplicate-words-loading');
    if (loadingDiv) {
        loadingDiv.remove();
    }
    
    if (!repeatedElements || repeatedElements.length === 0) {
        container.innerHTML = `
            <div class="chart-table-state">
                ${translations.noDuplicateWords || 'No duplicate words found'}
            </div>
        `;
        return;
    }
    
    let html = `
        <table class="chart-data-table-grid duplicate-words-grid">
            <thead>
                <tr>
                    <th>${translations.word || 'Word'}</th>
                    <th class="text-end">${translations.count || 'Count'}</th>
                    <th class="text-end">${translations.categories || 'Categories'}</th>
                    <th>${translations.categoryList || 'Category List'}</th>
                </tr>
            </thead>
            <tbody>
    `;
    
    repeatedElements.forEach((item) => {
        const categoriesList = item.categories && item.categories.length > 0 
            ? item.categories.join(', ') 
            : translations.noCategories || 'None';
        
        html += `
            <tr>
                <td class="chart-data-name">${escapeHtml(item.word || 'Unknown')}</td>
                <td class="text-end chart-data-count">${(item.count || 0).toLocaleString()}</td>
                <td class="text-end chart-data-count">${item.category_count || 0}</td>
                <td class="chart-data-name" title="${escapeHtml(categoriesList)}">${escapeHtml(categoriesList)}</td>
            </tr>
        `;
    });
    
    html += `</tbody></table>`;
    container.innerHTML = html;
}

// Backward compatibility
if (typeof window !== 'undefined') {
    window.loadClassificationCharts = loadClassificationCharts;
    window.switchDataType = switchDataType;
    window.switchChartType = switchChartType;
    window.filterChartData = filterChartData;
}

export default {
    loadClassificationCharts,
    switchDataType,
    switchChartType,
    filterChartData,
    renderClassificationChart,
    renderChartDataTable,
    renderDuplicateWords
};

