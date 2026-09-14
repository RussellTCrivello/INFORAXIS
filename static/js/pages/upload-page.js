/**
 * Upload Page JavaScript
 * Extracted from upload.html
 */

import { startProcessingProgressPolling, stopProcessingProgressPolling }
    from '../modules/ui/progress-tracker.js';

// Initialize chunked upload UI
document.addEventListener('DOMContentLoaded', function() {
    // Chunked upload initialization is handled by the module import in the HTML
    // This file handles the CLI form functionality

    // PROGRESS: this page ships a #processingProgressContainer block and
    // upload.css styles it, but nothing ever polled /upload/active-tasks - so
    // on the page where processing is actually started, the bar was dead markup
    // and the user saw no progress at all until they navigated to the dashboard.
    // Start the shared tracker as soon as the page is ready.
    startProcessingProgressPolling();
    
    const cliForm = document.getElementById('cliForm');
    const filePathInput = document.getElementById('filePathInput');
    const filePickerBtn = document.getElementById('filePickerBtn');
    const fileInput = document.getElementById('fileInput');
    const folderInput = document.getElementById('folderInput');
    const processBtn = document.getElementById('processBtn');
    const logContainer = document.getElementById('logContainer');
    const processStatus = document.getElementById('processStatus');
    
    let isProcessing = false;
    
    // File picker button handler
    if (filePickerBtn && fileInput && folderInput) {
        filePickerBtn.addEventListener('click', function() {
            // Show file picker dialog
            fileInput.click();
        });
    }
    
    // File input change handler
    if (fileInput) {
        fileInput.addEventListener('change', function(e) {
            if (isProcessing) {
                alert(window.translations?.cannotChangeFileSelection || 'Cannot change file selection while processing');
                return;
            }
            
            const files = e.target.files;
            if (files && files.length > 0) {
                // Handle file selection
                handleFileSelection(files);
            }
        });
    }
    
    // Folder input change handler
    if (folderInput) {
        folderInput.addEventListener('change', function(e) {
            if (isProcessing) {
                alert(window.translations?.cannotChangeFileSelection || 'Cannot change file selection while processing');
                return;
            }
            
            const files = e.target.files;
            if (files && files.length > 0) {
                // Handle folder selection
                handleFolderSelection(files);
            }
        });
    }
    
    // Form submit handler
    if (cliForm) {
        cliForm.addEventListener('submit', function(e) {
            e.preventDefault();
            
            if (isProcessing) {
                alert(window.translations?.processAlreadyRunning || 'Process already running. Please wait...');
                return;
            }
            
            const filePath = filePathInput?.value.trim();
            const sourceId = document.getElementById('sourceSelect')?.value;
            const sideId = document.getElementById('sideSelect')?.value;
            
            if (!filePath) {
                alert(window.translations?.pleaseEnterFilePath || 'Please enter a file path');
                return;
            }
            
            if (!sourceId || !sideId) {
                alert(window.translations?.pleaseSelectBothSourceAndSide || 'Please select both Source and Side');
                return;
            }
            
            startProcessing(filePath, sourceId, sideId);
        });
    }
    
    function handleFileSelection(files) {
        // Implementation for file selection
        if (files.length === 1) {
            const file = files[0];
            // Try to get full path (may not work in all browsers due to security)
            const path = file.webkitRelativePath || file.name;
            if (filePathInput) {
                filePathInput.value = path;
            }
            addLog('info', `${window.translations?.fileSelected || 'File selected'}: ${file.name}`);
        } else {
            // Multiple files - use directory path
            const commonPath = extractCommonPath(files);
            if (filePathInput && commonPath) {
                filePathInput.value = commonPath;
            }
            addLog('info', `${window.translations?.selectedFiles?.replace('{count}', files.length) || `Selected ${files.length} files`}`);
        }
    }
    
    function handleFolderSelection(files) {
        // Implementation for folder selection
        if (files.length > 0) {
            const commonPath = extractCommonPath(files);
            if (filePathInput && commonPath) {
                filePathInput.value = commonPath;
            }
            addLog('info', `${window.translations?.selectedFolderWithFiles?.replace('{count}', files.length) || `Selected folder with ${files.length} files`}`);
        }
    }
    
    function extractCommonPath(files) {
        // Try to extract common directory path from file list
        if (files.length === 0) return null;
        
        const paths = Array.from(files).map(f => f.webkitRelativePath || f.name);
        if (paths.length === 0) return null;
        
        // Find common prefix
        const firstPath = paths[0];
        let commonPrefix = firstPath.substring(0, firstPath.lastIndexOf('/') + 1);
        
        return commonPrefix || null;
    }
    
    async function startProcessing(filePath, sourceId, sideId) {
        isProcessing = true;
        if (processStatus) {
            processStatus.textContent = window.translations?.processingStatus || 'PROCESSING';
            processStatus.className = 'cli-status processing';
        }
        if (processBtn) {
            processBtn.disabled = true;
        }
        
        addLog('info', `${window.translations?.processing || 'Processing'}: ${filePath}`);
        addLog('info', `${window.translations?.sourceID || 'Source ID'}: ${sourceId}`);
        addLog('info', `${window.translations?.sideID || 'Side ID'}: ${sideId}`);
        
        try {
            // Use the correct endpoint for path-based processing
            const response = await fetch('/upload/process-path', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': document.querySelector('meta[name="csrf-token"]')?.getAttribute('content') || ''
                },
                body: JSON.stringify({
                    file_path: filePath,
                    source_id: parseInt(sourceId),
                    side_id: parseInt(sideId)
                })
            });
            
            // Check response status first
            if (!response.ok) {
                const errorData = await response.json().catch(() => ({ error: `HTTP ${response.status}: ${response.statusText}` }));
                throw new Error(errorData.error || `HTTP ${response.status}: ${response.statusText}`);
            }
            
            const data = await response.json();
            
            // Endpoint returns 202 Accepted with success: true and task_id
            if (data.success) {
                addLog('success', data.message || window.translations?.processCompletedSuccessfully || 'Processing started successfully!');
                if (data.task_id) {
                    addLog('info', `${window.translations?.taskID || 'Task ID'}: ${data.task_id}`);
                    addLog('info', window.translations?.processingInBackground || 'Processing is running in the background. Check task status for progress.');
                }
                // Pull the first progress snapshot straight away so the bar
                // appears the moment the job starts rather than up to one poll
                // interval later.
                window.processingProgressTracker?.refresh?.();
                if (processStatus) {
                    processStatus.textContent = window.translations?.processingStatus || 'PROCESSING';
                    processStatus.className = 'cli-status processing';
                }
            } else {
                throw new Error(data.error || window.translations?.processingFailed || 'Processing failed');
            }
        } catch (error) {
            console.error('Processing error:', error);
            addLog('error', `${window.translations?.error || 'Error'}: ${error.message || window.translations?.unknownError || 'Unknown error'}`);
            if (processStatus) {
                processStatus.textContent = window.translations?.errorStatus || 'ERROR';
                processStatus.className = 'cli-status error';
            }
        } finally {
            isProcessing = false;
            if (processBtn) {
                processBtn.disabled = false;
            }
            setTimeout(() => {
                if (processStatus) {
                    processStatus.textContent = window.translations?.ready || 'Ready';
                    processStatus.className = 'cli-status idle';
                }
            }, 3000);
        }
    }
    
    function addLog(type, message) {
        if (!logContainer) return;
        
        const logLine = document.createElement('div');
        logLine.className = `cli-log-line ${type}`;
        logLine.textContent = message;
        logContainer.appendChild(logLine);
        logContainer.scrollTop = logContainer.scrollHeight;
    }
    
    // Clear log function (called from HTML onclick)
    window.clearLog = function() {
        if (isProcessing) {
            alert(window.translations?.cannotClearLogWhileProcessing || 'Cannot clear log while processing');
            return;
        }
        
        if (logContainer) {
            logContainer.innerHTML = `
                <div class="cli-log-line prompt">${window.translations?.ready || 'Ready'}</div>
                <div class="cli-log-line info">${window.translations?.logCleared || 'Log cleared'}</div>
            `;
        }
    };
});

// Export default init function for universal-initializer
export default function init() {
    // The initialization is already handled in DOMContentLoaded above
    // This is just for compatibility with universal-initializer
    return Promise.resolve();
}

