/**
 * Chunked Upload Client
 * Handles large file uploads by breaking them into smaller chunks
 * Moved from chunked-upload.js with improved error handling
 */

import { apiPost, apiGet } from '../api/api-client.js';
import { getCSRFToken } from '../core/utils.js';

class ChunkedUploadClient {
    constructor(options = {}) {
        this.chunkSize = options.chunkSize || 5 * 1024 * 1024; // 5MB default
        this.maxRetries = options.maxRetries || 3;
        this.retryDelay = options.retryDelay || 1000; // 1 second
        this.onProgress = options.onProgress || (() => {});
        this.onComplete = options.onComplete || (() => {});
        this.onError = options.onError || (() => {});
        
        this.activeUploads = new Map();
    }
    
    /**
     * Calculate file hash using Web Crypto API
     */
    async calculateFileHash(file) {
        try {
            const buffer = await file.arrayBuffer();
            const hashBuffer = await crypto.subtle.digest('SHA-256', buffer);
            const hashArray = Array.from(new Uint8Array(hashBuffer));
            const hashHex = hashArray.map(b => b.toString(16).padStart(2, '0')).join('');
            return hashHex;
        } catch (error) {
            console.error('Error calculating file hash:', error);
            throw new Error('Failed to calculate file hash: ' + error.message);
        }
    }
    
    /**
     * Start chunked upload
     */
    async upload(file, sourceId, sideId, autoAnalyze = false) {
        try {
            // Validate inputs
            if (!file || !sourceId || !sideId) {
                throw new Error('Missing required parameters');
            }
            
            // Calculate file hash
            console.log('Calculating file hash...');
            const fileHash = await this.calculateFileHash(file);
            console.log(`File hash: ${fileHash}`);
            
            // Start upload session
            console.log('Starting upload session...');
            const session = await this.startUploadSession(
                file.name,
                file.size,
                fileHash,
                sourceId,
                sideId,
                autoAnalyze
            );
            
            if (!session.success) {
                throw new Error(session.error || 'Failed to start upload session');
            }
            
            const uploadId = session.upload_id;
            const totalChunks = session.total_chunks;
            const chunkSize = session.chunk_size;
            
            console.log(`Upload session started: ${uploadId}`);
            console.log(`Total chunks: ${totalChunks}, Chunk size: ${chunkSize}`);
            
            // Store upload info
            this.activeUploads.set(uploadId, {
                file,
                uploadId,
                totalChunks,
                chunkSize,
                uploadedChunks: 0,
                cancelled: false
            });
            
            // Upload chunks
            for (let chunkIndex = 0; chunkIndex < totalChunks; chunkIndex++) {
                // Check if cancelled
                const uploadInfo = this.activeUploads.get(uploadId);
                if (uploadInfo.cancelled) {
                    console.log('Upload cancelled');
                    throw new Error('Upload cancelled by user');
                }
                
                // Upload chunk with retry
                await this.uploadChunkWithRetry(
                    uploadId,
                    file,
                    chunkIndex,
                    chunkSize,
                    this.maxRetries
                );
                
                // Update progress
                uploadInfo.uploadedChunks = chunkIndex + 1;
                const progress = (uploadInfo.uploadedChunks / totalChunks) * 100;
                
                this.onProgress({
                    uploadId,
                    progress,
                    uploadedChunks: uploadInfo.uploadedChunks,
                    totalChunks,
                    fileName: file.name
                });
            }
            
            // Complete upload
            console.log('Completing upload...');
            const result = await this.completeUpload(uploadId);
            
            if (!result.success) {
                throw new Error(result.error || 'Failed to complete upload');
            }
            
            console.log('Upload completed successfully!');
            
            // Cleanup
            this.activeUploads.delete(uploadId);
            
            // Call completion callback
            this.onComplete(result);
            
            return result;
            
        } catch (error) {
            console.error('Upload error:', error);
            this.onError(error);
            throw error;
        }
    }
    
    /**
     * Start upload session
     */
    async startUploadSession(filename, totalSize, fileHash, sourceId, sideId, autoAnalyze) {
        try {
            const data = await apiPost('/upload/chunked/start', {
                filename,
                total_size: totalSize,
                file_hash: fileHash,
                source_id: sourceId,
                side_id: sideId,
                chunk_size: this.chunkSize,
                auto_analyze: autoAnalyze
            });
            return data;
        } catch (error) {
            console.error('Error starting upload session:', error);
            throw new Error('Failed to start upload session: ' + error.message);
        }
    }
    
    /**
     * Upload single chunk with retry
     */
    async uploadChunkWithRetry(uploadId, file, chunkIndex, chunkSize, retriesLeft) {
        try {
            await this.uploadChunk(uploadId, file, chunkIndex, chunkSize);
        } catch (error) {
            if (retriesLeft > 0) {
                console.warn(`Chunk ${chunkIndex} failed, retrying... (${retriesLeft} retries left)`);
                await this.sleep(this.retryDelay);
                return await this.uploadChunkWithRetry(
                    uploadId,
                    file,
                    chunkIndex,
                    chunkSize,
                    retriesLeft - 1
                );
            } else {
                throw new Error(`Failed to upload chunk ${chunkIndex} after ${this.maxRetries} retries: ${error.message}`);
            }
        }
    }
    
    /**
     * Upload single chunk
     */
    async uploadChunk(uploadId, file, chunkIndex, chunkSize) {
        try {
            const start = chunkIndex * chunkSize;
            const end = Math.min(start + chunkSize, file.size);
            const chunk = file.slice(start, end);
            
            const formData = new FormData();
            formData.append('chunk', chunk);
            
            const csrfToken = getCSRFToken();
            const response = await fetch(
                `/upload/chunked/${uploadId}/chunk/${chunkIndex}`,
                {
                    method: 'POST',
                    headers: {
                        'X-CSRFToken': csrfToken
                    },
                    body: formData
                }
            );
            
            if (!response.ok) {
                const errorData = await response.json().catch(() => ({}));
                throw new Error(errorData.error || `HTTP ${response.status}: ${response.statusText}`);
            }
            
            const result = await response.json();
            
            if (!result.success) {
                throw new Error(result.error || 'Chunk upload failed');
            }
            
            return result;
        } catch (error) {
            console.error(`Error uploading chunk ${chunkIndex}:`, error);
            throw error;
        }
    }
    
    /**
     * Complete upload
     */
    async completeUpload(uploadId) {
        try {
            const data = await apiPost(`/upload/chunked/${uploadId}/complete`, {});
            return data;
        } catch (error) {
            console.error('Error completing upload:', error);
            throw new Error('Failed to complete upload: ' + error.message);
        }
    }
    
    /**
     * Cancel upload
     */
    async cancelUpload(uploadId) {
        try {
            // Mark as cancelled locally
            const uploadInfo = this.activeUploads.get(uploadId);
            if (uploadInfo) {
                uploadInfo.cancelled = true;
            }
            
            // Cancel on server
            const data = await apiPost(`/upload/chunked/${uploadId}/cancel`, {});
            return data;
        } catch (error) {
            console.error('Error cancelling upload:', error);
            throw new Error('Failed to cancel upload: ' + error.message);
        }
    }
    
    /**
     * Get upload status
     */
    async getUploadStatus(uploadId) {
        try {
            const data = await apiGet(`/upload/chunked/${uploadId}/status`);
            return data;
        } catch (error) {
            console.error('Error getting upload status:', error);
            throw new Error('Failed to get upload status: ' + error.message);
        }
    }
    
    /**
     * Sleep utility
     */
    sleep(ms) {
        return new Promise(resolve => setTimeout(resolve, ms));
    }
    
    /**
     * Format file size
     */
    static formatFileSize(bytes) {
        if (bytes === 0) return '0 Bytes';
        
        const k = 1024;
        const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        
        return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i];
    }
    
    /**
     * Format upload speed
     */
    static formatSpeed(bytesPerSecond) {
        return this.formatFileSize(bytesPerSecond) + '/s';
    }
}

/**
 * UI Component for Chunked Upload
 */
class ChunkedUploadUI {
    constructor(containerId, options = {}) {
        this.container = document.getElementById(containerId);
        if (!this.container) {
            throw new Error(`Container element not found: ${containerId}`);
        }
        
        this.client = new ChunkedUploadClient({
            chunkSize: options.chunkSize || 5 * 1024 * 1024,
            onProgress: this.handleProgress.bind(this),
            onComplete: this.handleComplete.bind(this),
            onError: this.handleError.bind(this)
        });
        
        this.uploads = new Map();
        
        this.render();
    }
    
    render() {
        this.container.innerHTML = `
            <div class="chunked-upload-container">
                <div class="upload-controls">
                    <input type="file" id="chunked-file-input" multiple style="display: none;">
                    <button class="btn btn-primary" onclick="document.getElementById('chunked-file-input').click()">
                        <i class="bi bi-upload"></i> Select Files
                    </button>
                    <span class="upload-info"></span>
                </div>
                <div class="upload-list" id="chunked-upload-list"></div>
            </div>
        `;
        
        // Setup file input handler
        const fileInput = document.getElementById('chunked-file-input');
        fileInput.addEventListener('change', (e) => this.handleFileSelect(e));
    }
    
    async handleFileSelect(event) {
        const files = Array.from(event.target.files);
        
        if (files.length === 0) {
            return;
        }
        
        // Get source and side from form (assuming they exist)
        const sourceId = parseInt(document.getElementById('source_id')?.value);
        const sideId = parseInt(document.getElementById('side_id')?.value);
        const autoAnalyze = document.getElementById('auto_analyze')?.checked || false;
        
        if (!sourceId || !sideId) {
            if (window.showWarning) {
                window.showWarning('Please select source and side');
            } else {
                alert('Please select source and side');
            }
            return;
        }
        
        // Upload each file
        for (const file of files) {
            await this.uploadFile(file, sourceId, sideId, autoAnalyze);
        }
        
        // Clear file input
        event.target.value = '';
    }
    
    async uploadFile(file, sourceId, sideId, autoAnalyze) {
        const uploadId = Date.now() + '-' + Math.random().toString(36).substr(2, 9);
        
        // Add to UI
        this.addUploadToUI(uploadId, file);
        
        try {
            await this.client.upload(file, sourceId, sideId, autoAnalyze);
        } catch (error) {
            this.updateUploadStatus(uploadId, 'error', error.message);
        }
    }
    
    addUploadToUI(uploadId, file) {
        const list = document.getElementById('chunked-upload-list');
        
        const uploadDiv = document.createElement('div');
        uploadDiv.id = `upload-${uploadId}`;
        uploadDiv.className = 'upload-item';
        uploadDiv.innerHTML = `
            <div class="upload-item-header">
                <span class="file-name">${file.name}</span>
                <span class="file-size">${ChunkedUploadClient.formatFileSize(file.size)}</span>
            </div>
            <div class="progress">
                <div class="progress-bar" role="progressbar" style="width: 0%"></div>
            </div>
            <div class="upload-status">Preparing...</div>
        `;
        
        list.appendChild(uploadDiv);
        
        this.uploads.set(uploadId, {
            element: uploadDiv,
            startTime: Date.now()
        });
    }
    
    handleProgress(progressData) {
        const uploadDiv = this.uploads.get(progressData.uploadId)?.element;
        if (!uploadDiv) return;
        
        const progressBar = uploadDiv.querySelector('.progress-bar');
        const statusDiv = uploadDiv.querySelector('.upload-status');
        
        progressBar.style.width = `${progressData.progress}%`;
        progressBar.textContent = `${Math.round(progressData.progress)}%`;
        
        statusDiv.textContent = `Uploading chunk ${progressData.uploadedChunks}/${progressData.totalChunks}...`;
    }
    
    handleComplete(result) {
        console.log('Upload complete:', result);
        if (window.showSuccess) {
            window.showSuccess(`Upload complete: ${result.filename || 'File'}`);
        } else {
            alert(`Upload complete: ${result.filename || 'File'}`);
        }
    }
    
    handleError(error) {
        console.error('Upload error:', error);
        if (window.showError) {
            window.showError(`Upload error: ${error.message}`);
        } else {
            alert(`Upload error: ${error.message}`);
        }
    }
    
    updateUploadStatus(uploadId, status, message) {
        const uploadDiv = this.uploads.get(uploadId)?.element;
        if (!uploadDiv) return;
        
        const statusDiv = uploadDiv.querySelector('.upload-status');
        statusDiv.textContent = message;
        statusDiv.className = `upload-status ${status}`;
    }
}

// Export for use in other modules
export { ChunkedUploadClient, ChunkedUploadUI };

// Also expose globally for backward compatibility
if (typeof window !== 'undefined') {
    window.ChunkedUploadClient = ChunkedUploadClient;
    window.ChunkedUploadUI = ChunkedUploadUI;
}

