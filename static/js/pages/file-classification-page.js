/**
 * File Classification Page JavaScript
 * Extracted from Analysis/file_classification.html
 */

// Global state
let currentMethod = 'rule_based';
let isLoading = false;
let initialized = false;

function initializeFileClassificationPage() {
    if (initialized) return;
    initialized = true;
    console.log('File classification page loaded');
    
    // Initialize tab switching
    initializeTabs();
    
    // Initialize method selector
    initializeMethodSelector();
}

// Initialize page
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initializeFileClassificationPage, { once: true });
} else {
    initializeFileClassificationPage();
}

// Make functions available globally for onclick handlers immediately.
window.analyzeFolder = analyzeFolder;
window.analyzeFile = analyzeFile;
window.analyzeDatabase = analyzeDatabase;

// Tab switching
function initializeTabs() {
    const tabs = document.querySelectorAll('.analysis-tab');
    const panels = document.querySelectorAll('.analysis-panel');
    
    tabs.forEach(tab => {
        tab.addEventListener('click', function() {
            const panelId = this.getAttribute('data-panel');
            
            // Update active tab
            tabs.forEach(t => t.classList.remove('active'));
            this.classList.add('active');
            
            // Update active panel
            panels.forEach(p => p.classList.remove('active'));
            const targetPanel = document.getElementById(`panel-${panelId}`);
            if (targetPanel) {
                targetPanel.classList.add('active');
            }
        });
    });
}

// Method selector
function initializeMethodSelector() {
    const methodOptions = document.querySelectorAll('.method-option');
    
    methodOptions.forEach(option => {
        option.addEventListener('click', function() {
            // Update active method
            methodOptions.forEach(o => o.classList.remove('active'));
            this.classList.add('active');
            currentMethod = this.getAttribute('data-method');
        });
    });
}

// Get selected method from active panel
function getSelectedMethod(panelId) {
    const panel = document.getElementById(`panel-${panelId}`);
    if (!panel) return 'rule_based';
    
    const activeOption = panel.querySelector('.method-option.active');
    return activeOption ? activeOption.getAttribute('data-method') : 'rule_based';
}

// Show loading overlay
function showLoading(text = 'Processing...') {
    const overlay = document.getElementById('loadingOverlay');
    const loadingText = document.getElementById('loadingText');
    if (overlay) {
        overlay.style.display = 'flex';
        if (loadingText) loadingText.textContent = text;
    }
    isLoading = true;
}

// Hide loading overlay
function hideLoading() {
    const overlay = document.getElementById('loadingOverlay');
    if (overlay) {
        overlay.style.display = 'none';
    }
    isLoading = false;
}


function numericValue(...values) {
    for (const value of values) {
        const number = Number(value);
        if (Number.isFinite(number)) return number;
    }
    return 0;
}

function normalizeClassificationData(data = {}) {
    const classifications = Array.isArray(data.classifications) ? data.classifications : [];
    const normalizedClassifications = classifications.map((cat) => ({
        category: cat.category || 'Uncategorized',
        fileCount: numericValue(cat.fileCount, cat.file_count),
        totalKeywords: numericValue(cat.totalKeywords, cat.total_keywords),
        percentage: numericValue(cat.percentage)
    }));
    const totalFiles = numericValue(data.totalFiles, data.total_files);
    const categorizedFiles = numericValue(data.categorizedFiles, data.categorized_files);
    const uncategorizedFiles = numericValue(data.uncategorizedFiles, data.uncategorized_files, totalFiles - categorizedFiles);
    return {
        ...data,
        totalFiles,
        categorizedFiles,
        uncategorizedFiles: Math.max(0, uncategorizedFiles),
        classifications: normalizedClassifications
    };
}

function renderError(container, message) {
    if (!container) return;
    container.innerHTML = `
        <div class="alert alert-danger">
            <i class="bi bi-exclamation-triangle me-2" aria-hidden="true"></i>
            Error: ${escapeHtml(message || 'Analysis failed')}
        </div>
    `;
    container.style.display = 'block';
}

// Analyze folder
async function analyzeFolder() {
    if (isLoading) return;
    
    const folderPath = document.getElementById('folderPathInput').value.trim();
    if (!folderPath) {
        alert('Please enter a folder path');
        return;
    }
    
    const method = getSelectedMethod('folder');
    const resultsDiv = document.getElementById('folderResults');
    
    showLoading('Analyzing folder...');
    resultsDiv.style.display = 'none';
    
    try {
        // Use the classification API endpoint
        const response = await fetch(`/api/analytics/path/classifications?path=${encodeURIComponent(folderPath)}`);
        const data = await response.json();
        
        if (data.success) {
            displayFolderResults(data, resultsDiv);
        } else {
            throw new Error(data.error || 'Analysis failed');
        }
    } catch (error) {
        console.error('Error analyzing folder:', error);
        renderError(resultsDiv, error.message);
    } finally {
        hideLoading();
    }
}

// Display folder results
function displayFolderResults(data, container) {
    const normalized = normalizeClassificationData(data);
    const classifications = normalized.classifications;
    const totalFiles = normalized.totalFiles;
    const categorizedFiles = normalized.categorizedFiles;
    const uncategorizedFiles = normalized.uncategorizedFiles;
    
    let html = `
        <h4 class="mb-3"><i class="bi bi-graph-up me-2"></i>Analysis Results</h4>
        <div class="row mb-3">
            <div class="col-md-4">
                <div class="card">
                    <div class="card-body">
                        <h5 class="card-title">Total Files</h5>
                        <p class="card-text display-6">${totalFiles}</p>
                    </div>
                </div>
            </div>
            <div class="col-md-4">
                <div class="card">
                    <div class="card-body">
                        <h5 class="card-title">Categorized</h5>
                        <p class="card-text display-6 text-success">${categorizedFiles}</p>
                    </div>
                </div>
            </div>
            <div class="col-md-4">
                <div class="card">
                    <div class="card-body">
                        <h5 class="card-title">Uncategorized</h5>
                        <p class="card-text display-6 text-warning">${uncategorizedFiles}</p>
                    </div>
                </div>
            </div>
        </div>
    `;
    
    if (classifications.length > 0) {
        html += `
            <h5 class="mb-3">Classification Breakdown</h5>
            <div class="table-responsive">
                <table class="table table-striped">
                    <thead>
                        <tr>
                            <th>Category</th>
                            <th>Files</th>
                            <th>Percentage</th>
                            <th>Keywords</th>
                        </tr>
                    </thead>
                    <tbody>
        `;
        
        classifications.forEach(cat => {
            html += `
                <tr>
                    <td><strong>${escapeHtml(cat.category)}</strong></td>
                    <td>${cat.fileCount}</td>
                    <td>${cat.percentage}%</td>
                    <td>${cat.totalKeywords}</td>
                </tr>
            `;
        });
        
        html += `
                    </tbody>
                </table>
            </div>
        `;
    } else {
        html += `
            <div class="alert alert-info">
                <i class="bi bi-info-circle me-2"></i>
                No classifications found for this folder.
            </div>
        `;
    }
    
    container.innerHTML = html;
    container.style.display = 'block';
}

// Analyze file
async function analyzeFile() {
    if (isLoading) return;
    
    const fileId = document.getElementById('fileIdInput').value.trim();
    if (!fileId) {
        alert('Please enter a file ID');
        return;
    }
    
    const method = getSelectedMethod('file');
    const resultsDiv = document.getElementById('fileResults');
    
    showLoading('Analyzing file...');
    resultsDiv.style.display = 'none';
    
    try {
        // The classification endpoint carries the exact aggregate data this
        // panel renders. Use the explicit file_id scope so the backend does not
        // accidentally treat the numeric ID as a literal filesystem path.
        const classificationResponse = await fetch(`/api/analytics/path/classifications?file_id=${encodeURIComponent(fileId)}`);
        if (!classificationResponse.ok) throw new Error(`HTTP ${classificationResponse.status}`);
        const classificationData = await classificationResponse.json();
        
        if (classificationData.success) {
            displayFileResults(classificationData, fileId, resultsDiv);
        } else {
            throw new Error(classificationData.error || 'Analysis failed');
        }
    } catch (error) {
        console.error('Error analyzing file:', error);
        renderError(resultsDiv, error.message);
    } finally {
        hideLoading();
    }
}

// Display file results
function displayFileResults(data, fileId, container) {
    const normalized = normalizeClassificationData(data);
    const classifications = normalized.classifications;
    
    let html = `
        <h4 class="mb-3"><i class="bi bi-file-earmark-text me-2"></i>File Analysis Results</h4>
        <div class="alert alert-info">
            <i class="bi bi-info-circle me-2"></i>
            File ID: ${escapeHtml(fileId)}
        </div>
    `;
    
    if (classifications.length > 0) {
        html += `
            <h5 class="mb-3">Classifications</h5>
            <div class="list-group">
        `;
        
        classifications.forEach(cat => {
            html += `
                <div class="list-group-item">
                    <div class="d-flex justify-content-between align-items-center">
                        <div>
                            <h6 class="mb-1">${escapeHtml(cat.category)}</h6>
                            <small class="text-muted">${cat.totalKeywords} keywords found</small>
                        </div>
                        <span class="badge bg-primary">${cat.percentage}%</span>
                    </div>
                </div>
            `;
        });
        
        html += `</div>`;
    } else {
        html += `
            <div class="alert alert-warning">
                <i class="bi bi-exclamation-triangle me-2"></i>
                No classifications found for this file.
            </div>
        `;
    }
    
    container.innerHTML = html;
    container.style.display = 'block';
}

// Analyze database
async function analyzeDatabase() {
    if (isLoading) return;
    
    const limit = parseInt(document.getElementById('dbLimitInput').value) || 1000;
    if (limit < 1 || limit > 10000) {
        alert('Limit must be between 1 and 10000');
        return;
    }
    
    const method = getSelectedMethod('database');
    const resultsDiv = document.getElementById('databaseResults');
    
    showLoading('Analyzing database... This may take a while.');
    resultsDiv.style.display = 'none';
    
    try {
        // For database analysis, we'll get overall statistics
        // This is a simplified version - you may want to create a dedicated endpoint
        const response = await fetch(`/api/analytics/path/classifications?path=*&limit=${encodeURIComponent(limit)}`);
        const data = await response.json();
        
        if (data.success) {
            displayDatabaseResults(data, limit, resultsDiv);
        } else {
            throw new Error(data.error || 'Analysis failed');
        }
    } catch (error) {
        console.error('Error analyzing database:', error);
        renderError(resultsDiv, error.message);
    } finally {
        hideLoading();
    }
}

// Display database results
function displayDatabaseResults(data, limit, container) {
    const normalized = normalizeClassificationData(data);
    const classifications = normalized.classifications;
    const totalFiles = normalized.totalFiles;
    
    let html = `
        <h4 class="mb-3"><i class="bi bi-database me-2"></i>Database Analysis Results</h4>
        <div class="alert alert-info">
            <i class="bi bi-info-circle me-2"></i>
            Analyzed up to ${limit} files. Total files in database: ${totalFiles}
        </div>
    `;
    
    if (classifications.length > 0) {
        html += `
            <h5 class="mb-3">Top Classifications</h5>
            <div class="table-responsive">
                <table class="table table-striped">
                    <thead>
                        <tr>
                            <th>Category</th>
                            <th>Files</th>
                            <th>Percentage</th>
                            <th>Keywords</th>
                        </tr>
                    </thead>
                    <tbody>
        `;
        
        classifications.forEach(cat => {
            html += `
                <tr>
                    <td><strong>${escapeHtml(cat.category)}</strong></td>
                    <td>${cat.fileCount}</td>
                    <td>${cat.percentage}%</td>
                    <td>${cat.totalKeywords}</td>
                </tr>
            `;
        });
        
        html += `
                    </tbody>
                </table>
            </div>
        `;
    } else {
        html += `
            <div class="alert alert-warning">
                <i class="bi bi-exclamation-triangle me-2"></i>
                No classifications found.
            </div>
        `;
    }
    
    container.innerHTML = html;
    container.style.display = 'block';
}

// Utility: Escape HTML
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

export default function init() {
    initializeFileClassificationPage();
}

