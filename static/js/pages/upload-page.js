/**
 * Upload Page JavaScript
 * Extracted from upload.html
 */

import { startProcessingProgressPolling, stopProcessingProgressPolling }
    from '../modules/ui/progress-tracker.js';

let initialized = false;
let isProcessing = false;
let resetStatusTimer = null;

function normalizeTranslation(value) {
    if (typeof value !== 'string') return value;
    // Some legacy templates serialized already-jsonified strings inside a
    // second JSON payload. Unwrap that shape so UI text is never rendered with
    // literal quote marks.
    if ((value.startsWith('"') && value.endsWith('"')) ||
        (value.startsWith("'") && value.endsWith("'"))) {
        try {
            return JSON.parse(value);
        } catch (error) {
            return value.slice(1, -1);
        }
    }
    return value;
}

function loadUploadTranslations() {
    const el = document.getElementById('upload-page-translations');
    if (!el) return;
    try {
        const data = JSON.parse(el.textContent || '{}');
        window.translations = window.translations || {};
        Object.entries(data).forEach(([key, value]) => {
            window.translations[key] = normalizeTranslation(value);
        });
    } catch (error) {
        console.warn('Upload translations could not be parsed', error);
    }
}

function t(key, fallback) {
    return window.translations?.[key] || fallback;
}

function getElements() {
    return {
        cliForm: document.getElementById('cliForm'),
        filePathInput: document.getElementById('filePathInput'),
        filePickerBtn: document.getElementById('filePickerBtn'),
        folderPickerBtn: document.getElementById('folderPickerBtn'),
        fileInput: document.getElementById('fileInput'),
        folderInput: document.getElementById('folderInput'),
        processBtn: document.getElementById('processBtn'),
        logContainer: document.getElementById('logContainer'),
        processStatus: document.getElementById('processStatus')
    };
}

function setStatus(statusEl, text, className) {
    if (!statusEl) return;
    statusEl.textContent = text;
    statusEl.className = `processor-status ${className}`;
}

function addLog(type, message) {
    const { logContainer } = getElements();
    if (!logContainer) return;

    const logLine = document.createElement('div');
    logLine.className = `processor-log-line ${type}`;
    logLine.textContent = message;
    logContainer.appendChild(logLine);
    logContainer.scrollTop = logContainer.scrollHeight;
}

function extractCommonPath(files) {
    if (!files.length) return null;

    const paths = Array.from(files).map(f => f.webkitRelativePath || f.name);
    if (!paths.length) return null;

    const firstPath = paths[0];
    return firstPath.substring(0, firstPath.lastIndexOf('/') + 1) || null;
}

function handleFileSelection(files) {
    const { filePathInput } = getElements();
    if (files.length === 1) {
        const file = files[0];
        const path = file.webkitRelativePath || file.name;
        if (filePathInput) filePathInput.value = path;
        addLog('info', `${t('fileSelected', 'File selected')}: ${file.name}`);
        return;
    }

    const commonPath = extractCommonPath(files);
    if (filePathInput && commonPath) filePathInput.value = commonPath;
    addLog('info', t('selectedFiles', `Selected ${files.length} files`).replace('{count}', files.length));
}

function handleFolderSelection(files) {
    const { filePathInput } = getElements();
    if (!files.length) return;

    const commonPath = extractCommonPath(files);
    if (filePathInput && commonPath) filePathInput.value = commonPath;
    addLog('info', t('selectedFolderWithFiles', `Selected folder with ${files.length} files`).replace('{count}', files.length));
}

async function startProcessing(filePath, sourceId, sideId) {
    const { processBtn, processStatus } = getElements();
    isProcessing = true;
    if (resetStatusTimer) {
        clearTimeout(resetStatusTimer);
        resetStatusTimer = null;
    }
    setStatus(processStatus, t('processingStatus', 'PROCESSING'), 'processing');
    if (processBtn) processBtn.disabled = true;

    addLog('info', `${t('processing', 'Processing')}: ${filePath}`);
    addLog('info', `${t('sourceID', 'Source ID')}: ${sourceId}`);
    addLog('info', `${t('sideID', 'Side ID')}: ${sideId}`);

    try {
        const response = await fetch('/upload/process-path', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': document.querySelector('meta[name="csrf-token"]')?.getAttribute('content') || ''
            },
            body: JSON.stringify({
                file_path: filePath,
                source_id: parseInt(sourceId, 10),
                side_id: parseInt(sideId, 10)
            })
        });

        if (!response.ok) {
            const errorData = await response.json().catch(() => ({ error: `HTTP ${response.status}: ${response.statusText}` }));
            throw new Error(errorData.error || `HTTP ${response.status}: ${response.statusText}`);
        }

        const data = await response.json();

        if (!data.success) {
            throw new Error(data.error || t('processingFailed', 'Processing failed'));
        }

        addLog('success', data.message || t('processCompletedSuccessfully', 'Processing started successfully!'));
        if (data.task_id) {
            addLog('info', `${t('taskID', 'Task ID')}: ${data.task_id}`);
            addLog('info', t('processingInBackground', 'Processing is running in the background. Check task status for progress.'));
        }

        // Pull the first progress snapshot straight away so the bar appears the
        // moment the job starts rather than waiting for the next poll interval.
        window.processingProgressTracker?.refresh?.();
        setStatus(processStatus, t('processingStatus', 'PROCESSING'), 'processing');
    } catch (error) {
        console.error('Processing error:', error);
        addLog('error', `${t('error', 'Error')}: ${error.message || t('unknownError', 'Unknown error')}`);
        setStatus(processStatus, t('errorStatus', 'ERROR'), 'error');
    } finally {
        isProcessing = false;
        if (processBtn) processBtn.disabled = false;
        resetStatusTimer = setTimeout(() => {
            setStatus(getElements().processStatus, t('ready', 'Ready'), 'idle');
            resetStatusTimer = null;
        }, 3000);
    }
}

function setupHandlers() {
    const { cliForm, filePathInput, filePickerBtn, folderPickerBtn, fileInput, folderInput } = getElements();

    filePickerBtn?.addEventListener('click', () => fileInput?.click());
    folderPickerBtn?.addEventListener('click', () => folderInput?.click());

    fileInput?.addEventListener('change', (event) => {
        if (isProcessing) {
            alert(t('cannotChangeFileSelection', 'Cannot change file selection while processing'));
            return;
        }
        if (event.target.files?.length) handleFileSelection(event.target.files);
    });

    folderInput?.addEventListener('change', (event) => {
        if (isProcessing) {
            alert(t('cannotChangeFileSelection', 'Cannot change file selection while processing'));
            return;
        }
        if (event.target.files?.length) handleFolderSelection(event.target.files);
    });

    cliForm?.addEventListener('submit', (event) => {
        event.preventDefault();

        if (isProcessing) {
            alert(t('processAlreadyRunning', 'Process already running. Please wait...'));
            return;
        }

        const filePath = filePathInput?.value.trim();
        const sourceId = document.getElementById('sourceSelect')?.value;
        const sideId = document.getElementById('sideSelect')?.value;

        if (!filePath) {
            alert(t('pleaseEnterFilePath', 'Please enter a file path'));
            return;
        }

        if (!sourceId || !sideId) {
            alert(t('pleaseSelectBothSourceAndSide', 'Please select both Source and Side'));
            return;
        }

        startProcessing(filePath, sourceId, sideId);
    });
}

function initializeUploadPage() {
    if (initialized) {
        console.debug('Upload page already initialized, skipping duplicate setup');
        return;
    }
    initialized = true;
    loadUploadTranslations();

    // PROGRESS: this page ships a #processingProgressContainer block and
    // upload.css styles it, but nothing ever polled /upload/active-tasks - so
    // on the page where processing is actually started, the bar was dead markup.
    startProcessingProgressPolling();
    window.addEventListener('pagehide', stopProcessingProgressPolling, { once: true });

    setupHandlers();

    window.clearLog = function() {
        const { logContainer } = getElements();
        if (isProcessing) {
            alert(t('cannotClearLogWhileProcessing', 'Cannot clear log while processing'));
            return;
        }

        if (!logContainer) return;
        logContainer.replaceChildren();
        ['prompt', 'info'].forEach((type, index) => {
            const line = document.createElement('div');
            line.className = `processor-log-line ${type}`;
            line.textContent = index === 0 ? t('ready', 'Ready') : t('logCleared', 'Log cleared');
            logContainer.appendChild(line);
        });
    };
}

export default function init() {
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initializeUploadPage, { once: true });
    } else {
        initializeUploadPage();
    }
}

// Direct module fallback: upload.html includes this file explicitly, while the
// universal initializer skips explicit page modules to prevent duplicate work.
init();
