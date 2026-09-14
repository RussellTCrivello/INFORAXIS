/**
 * Email Words Page JavaScript
 * Handles initialization and interactions for the email words page
 */

// Global state for sorting
let currentSortBy = 'word';
let currentSortOrder = 'asc';

function initializeEmailWordsPage() {
    // Load filters from JSON embedded in the page (template-safe)
    const filtersDataEl = document.getElementById('emailWordsFiltersData');
    if (filtersDataEl && filtersDataEl.textContent) {
        try {
            window.emailWordsFilters = JSON.parse(filtersDataEl.textContent);
        } catch (e) {
            window.emailWordsFilters = window.emailWordsFilters || {};
        }
    } else {
        window.emailWordsFilters = window.emailWordsFilters || {};
    }
    
    // Get current sort parameters from URL
    const urlParams = new URLSearchParams(window.location.search);
    currentSortBy = urlParams.get('sort_by') || 'word';
    currentSortOrder = urlParams.get('sort_order') || 'asc';
    updateSortIcons();

    // Wire domain dropdown -> domain input, then submit
    const domainSelect = document.getElementById('domainSelect');
    const domainInput = document.getElementById('domainInput');
    const filtersForm = document.getElementById('emailFiltersForm');

    if (domainSelect && domainInput && filtersForm) {
        domainSelect.addEventListener('change', function () {
            if (!this.value) return;
            domainInput.value = this.value;
            filtersForm.submit();
        });
    }

    // Click domain pill in table -> set domain and submit
    document.querySelectorAll('.domain-pill').forEach((el) => {
        el.addEventListener('click', function () {
            if (!domainInput || !filtersForm) return;
            const d = this.getAttribute('data-domain');
            if (!d) return;
            domainInput.value = d;
            filtersForm.submit();
        });
    });
    
    // Add click handlers for sortable columns
    document.querySelectorAll('.sortable').forEach((th) => {
        th.style.cursor = 'pointer';
        th.addEventListener('click', function() {
            const sortColumn = this.getAttribute('data-sort');
            sortTable(sortColumn);
        });
    });
    
    // Add hover effect for sortable columns
    document.querySelectorAll('.sortable').forEach((th) => {
        th.addEventListener('mouseenter', function() {
            this.style.backgroundColor = '#f8f9fa';
        });
        th.addEventListener('mouseleave', function() {
            if (!this.querySelector('.sort-icon.text-primary')) {
                this.style.backgroundColor = '';
            }
        });
    });
    
    // Update totals display immediately
    updateTotalsDisplay();
}

// Update totals display
function updateTotalsDisplay() {
    const showingCount = document.getElementById('showingCount');
    const totalCount = document.getElementById('totalCount');
    const emailRows = document.querySelectorAll('.email-row');
    
    if (showingCount && emailRows.length > 0) {
        showingCount.textContent = emailRows.length;
    }
}

// Sort table by column
function sortTable(column) {
    if (currentSortBy === column) {
        // Toggle sort order
        currentSortOrder = currentSortOrder === 'asc' ? 'desc' : 'asc';
    } else {
        // New column, default to ascending
        currentSortBy = column;
        currentSortOrder = 'asc';
    }
    
    // Reload page with new sort parameters
    const url = new URL(window.location.href);
    url.searchParams.set('sort_by', currentSortBy);
    url.searchParams.set('sort_order', currentSortOrder);
    url.searchParams.set('page', '1'); // Reset to first page
    window.location.href = url.toString();
}

// Update sort icons
function updateSortIcons() {
    document.querySelectorAll('.sortable').forEach((th) => {
        const column = th.getAttribute('data-sort');
        const icon = th.querySelector('.sort-icon');
        if (icon) {
            if (currentSortBy === column) {
                icon.className = `bi bi-arrow-${currentSortOrder === 'asc' ? 'up' : 'down'} ms-1 sort-icon text-primary`;
            } else {
                icon.className = 'bi bi-arrow-down-up ms-1 sort-icon text-muted';
            }
        }
    });
}

// Change per page
function changePerPage(value) {
    const url = new URL(window.location.href);
    url.searchParams.set('per_page', value);
    url.searchParams.set('page', '1'); // Reset to first page
    window.location.href = url.toString();
}

// Note:
// - The page now uses server-side filtering via GET params (q/domain/domain_mode).
// - We intentionally do NOT do client-side row hiding on input, so counts/pagination stay correct.

function clearSearch() {
    const searchInput = document.getElementById('searchInput');
    if (searchInput) searchInput.value = '';
}

function copyEmail(email) {
    navigator.clipboard.writeText(email).then(() => {
        // Show temporary success message
        const btn = event.target.closest('button');
        const originalHTML = btn.innerHTML;
        btn.innerHTML = '<i class="bi bi-check"></i>';
        btn.classList.remove('btn-outline-primary');
        btn.classList.add('btn-success');
        
        setTimeout(() => {
            btn.innerHTML = originalHTML;
            btn.classList.remove('btn-success');
            btn.classList.add('btn-outline-primary');
        }, 1000);
    });
}

async function copyToClipboard() {
    // Fetch ALL filtered emails from database
    try {
        const button = event.target.closest('button');
        const originalHTML = button.innerHTML;
        button.innerHTML = '<i class="bi bi-hourglass-split"></i> Loading...';
        button.disabled = true;

        const params = new URLSearchParams(window.emailWordsFilters || {});
        const response = await fetch(`/api/email-words/all?${params.toString()}`);
        const data = await response.json();
        
        if (!data.success) {
            throw new Error(data.error || 'Failed to fetch emails');
        }
        
        const emails = data.emails.map(item => item.email).join('\n');
        
        await navigator.clipboard.writeText(emails);
        
        button.innerHTML = '<i class="bi bi-check-circle"></i> Copied!';
        button.classList.remove('btn-outline-secondary');
        button.classList.add('btn-success');
        
        setTimeout(() => {
            button.innerHTML = originalHTML;
            button.classList.remove('btn-success');
            button.classList.add('btn-outline-secondary');
            button.disabled = false;
        }, 2000);
        
        // Show toast notification
        showToast(`Copied ${data.total} email addresses to clipboard!`, 'success');
    } catch (error) {
        console.error('Error copying emails:', error);
        alert(`Error copying emails: ${error.message}`);
        const button = event.target.closest('button');
        button.innerHTML = '<i class="bi bi-clipboard"></i> Copy All';
        button.disabled = false;
    }
}

function searchInFiles(email) {
    // Redirect to advanced search with email pre-filled
    window.location.href = `/search/advanced?q=${encodeURIComponent(email)}`;
}

// Show files containing an email address in a modal
async function showEmailFiles(email) {
    // Get Bootstrap modal instance (works with both Bootstrap 4 and 5)
    const modalElement = document.getElementById('emailFilesModal');
    let modal;
    if (typeof bootstrap !== 'undefined' && bootstrap.Modal) {
        modal = new bootstrap.Modal(modalElement);
    } else if (typeof $ !== 'undefined' && $.fn.modal) {
        // Fallback to jQuery Bootstrap modal
        modal = $(modalElement);
    } else {
        // Fallback: show modal manually
        modalElement.style.display = 'block';
        modalElement.classList.add('show');
        document.body.classList.add('modal-open');
    }
    const modalBody = document.getElementById('emailFilesModalBody');
    const modalTitle = document.getElementById('modalEmailAddress');
    const modalFileCount = document.getElementById('modalFileCount');
    
    // Set email in title
    modalTitle.textContent = email;
    
    // Show loading state
    modalBody.innerHTML = `
        <div class="text-center py-4">
            <div class="spinner-border text-primary" role="status">
                <span class="visually-hidden">Loading...</span>
            </div>
            <p class="mt-2">Loading files...</p>
        </div>
    `;
    
    // Show modal
    if (modal && typeof modal.show === 'function') {
        modal.show();
    } else if (modal && typeof modal.modal === 'function') {
        modal.modal('show');
    } else {
        // Manual show
        modalElement.style.display = 'block';
        modalElement.classList.add('show');
        document.body.classList.add('modal-open');
    }
    
    try {
        // Fetch files containing this email
        const response = await fetch(`/api/email-words/files?email=${encodeURIComponent(email)}&limit=500`);
        const data = await response.json();
        
        if (!data.success) {
            throw new Error(data.error || 'Failed to fetch files');
        }
        
        // Update file count
        modalFileCount.textContent = data.total || data.files.length;
        
        if (data.files && data.files.length > 0) {
            // Render files list
            renderEmailFiles(data.files, email);
        } else {
            modalBody.innerHTML = `
                <div class="text-center py-5">
                    <i class="bi bi-inbox display-4 text-muted d-block mb-3"></i>
                    <h5>No Files Found</h5>
                    <p class="text-muted">No files contain this email address.</p>
                </div>
            `;
        }
    } catch (error) {
        console.error('Error loading email files:', error);
        modalBody.innerHTML = `
            <div class="alert alert-danger">
                <i class="bi bi-exclamation-triangle me-2"></i>
                <strong>Error loading files:</strong> ${error.message}
            </div>
        `;
    }
}

// Render files list in modal
function renderEmailFiles(files, email) {
    const modalBody = document.getElementById('emailFilesModalBody');
    
    let html = `
        <div class="mb-3 p-3 bg-light rounded">
            <div class="d-flex justify-content-between align-items-center">
                <div>
                    <strong>${files.length}</strong> ${files.length === 1 ? 'file' : 'files'} containing 
                    <code>${email}</code>
                </div>
            </div>
        </div>
        <div class="list-group">
    `;
    
    files.forEach((file, index) => {
        const fileIcon = getFileIcon(file.type);
        const fileSize = formatFileSize(file.size);
        const fileDate = file.date ? new Date(file.date).toLocaleDateString() : 'N/A';
        const statusBadge = file.status === 'Read' 
            ? '<span class="badge bg-success">Read</span>' 
            : '<span class="badge bg-secondary">Unread</span>';
        
        html += `
            <div class="list-group-item list-group-item-action" 
                 onclick="window.open('/file/${file.id}', '_blank')"
                 style="cursor: pointer;">
                <div class="d-flex w-100 justify-content-between align-items-start">
                    <div class="flex-grow-1">
                        <div class="d-flex align-items-center mb-2">
                            ${fileIcon}
                            <h6 class="mb-0 ms-2">${escapeHtml(file.name)}</h6>
                            ${statusBadge}
                        </div>
                        <div class="small text-muted mb-1">
                            <i class="bi bi-folder"></i> ${escapeHtml(file.path || 'N/A')}
                        </div>
                        <div class="small">
                            <span class="badge bg-info me-2">
                                <i class="bi bi-file-earmark"></i> ${file.type.toUpperCase()}
                            </span>
                            <span class="badge bg-secondary me-2">
                                <i class="bi bi-hdd"></i> ${fileSize}
                            </span>
                            <span class="badge bg-secondary me-2">
                                <i class="bi bi-calendar"></i> ${fileDate}
                            </span>
                            ${file.word_count ? `<span class="badge bg-primary">
                                <i class="bi bi-envelope"></i> ${file.word_count} occurrence${file.word_count !== 1 ? 's' : ''}
                            </span>` : ''}
                        </div>
                        ${file.source || file.side ? `
                            <div class="small mt-1">
                                ${file.source ? `<span class="badge bg-outline-primary me-1">Source: ${escapeHtml(file.source)}</span>` : ''}
                                ${file.side ? `<span class="badge bg-outline-secondary">Side: ${escapeHtml(file.side)}</span>` : ''}
                            </div>
                        ` : ''}
                    </div>
                    <div class="ms-3">
                        <button class="btn btn-sm btn-outline-primary" 
                                onclick="event.stopPropagation(); window.open('/file/${file.id}', '_blank')"
                                title="View file">
                            <i class="bi bi-eye"></i>
                        </button>
                    </div>
                </div>
            </div>
        `;
    });
    
    html += `</div>`;
    
    modalBody.innerHTML = html;
}

// Helper functions
function getFileIcon(fileType) {
    const icons = {
        'pdf': 'bi-file-pdf text-danger',
        'doc': 'bi-file-word text-primary',
        'docx': 'bi-file-word text-primary',
        'xls': 'bi-file-excel text-success',
        'xlsx': 'bi-file-excel text-success',
        'txt': 'bi-file-text',
        'eml': 'bi-envelope text-info',
        'msg': 'bi-envelope text-info',
        'html': 'bi-file-code text-warning',
        'htm': 'bi-file-code text-warning'
    };
    const icon = icons[fileType?.toLowerCase()] || 'bi-file-earmark';
    return `<i class="bi ${icon} fs-4"></i>`;
}

function formatFileSize(bytes) {
    if (!bytes || bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i];
}

function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

async function exportData() {
    // Fetch ALL filtered emails from database for export
    try {
        const button = event.target.closest('button');
        const originalHTML = button.innerHTML;
        button.innerHTML = '<i class="bi bi-hourglass-split"></i> Exporting...';
        button.disabled = true;

        const params = new URLSearchParams(window.emailWordsFilters || {});
        const response = await fetch(`/api/email-words/all?${params.toString()}`);
        const data = await response.json();
        
        if (!data.success) {
            throw new Error(data.error || 'Failed to fetch emails');
        }
        
        // Create CSV content with usage counts
        let csvContent = "Email Address,Usage Count,Files\n";
        data.emails.forEach((item, index) => {
            csvContent += `"${item.email}",${item.usage_count},${item.usage_count}\n`;
        });
        
        // Create and download file
        const blob = new Blob([csvContent], { type: 'text/csv' });
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `email_words_export_${new Date().toISOString().split('T')[0]}.csv`;
        a.click();
        window.URL.revokeObjectURL(url);
        
        button.innerHTML = '<i class="bi bi-check-circle"></i> Exported!';
        button.classList.remove('btn-outline-primary');
        button.classList.add('btn-success');
        
        setTimeout(() => {
            button.innerHTML = originalHTML;
            button.classList.remove('btn-success');
            button.classList.add('btn-outline-primary');
            button.disabled = false;
        }, 2000);
        
        // Show toast notification
        showToast(`Exported ${data.total} email addresses to CSV!`, 'success');
    } catch (error) {
        console.error('Error exporting emails:', error);
        alert(`Error exporting emails: ${error.message}`);
        const button = event.target.closest('button');
        button.innerHTML = '<i class="bi bi-download"></i> Export CSV';
        button.disabled = false;
    }
}

// Toast notification helper
function showToast(message, type = 'info') {
    const toastContainer = document.getElementById('toastContainer') || createToastContainer();
    const toast = document.createElement('div');
    toast.className = `alert alert-${type === 'success' ? 'success' : 'info'} alert-dismissible fade show`;
    toast.style.cssText = 'position: fixed; top: 20px; right: 20px; z-index: 9999; min-width: 300px;';
    toast.innerHTML = `
        <i class="bi bi-${type === 'success' ? 'check-circle' : 'info-circle'} me-2"></i>
        ${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
    `;
    toastContainer.appendChild(toast);
    setTimeout(() => toast.remove(), 4000);
}

function createToastContainer() {
    const container = document.createElement('div');
    container.id = 'toastContainer';
    document.body.appendChild(container);
    return container;
}

function copyAllEmails() {
    copyToClipboard();
}

// Add to contacts
function addToContacts(email) {
    fetch('/contacts/add', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({email: email})
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            const btn = event.target.closest('button');
            const originalHTML = btn.innerHTML;
            btn.innerHTML = '<i class="bi bi-check"></i>';
            btn.classList.remove('btn-outline-success');
            btn.classList.add('btn-success');
            
            setTimeout(() => {
                btn.innerHTML = originalHTML;
                btn.classList.remove('btn-success');
                btn.classList.add('btn-outline-success');
            }, 2000);
        }
    })
    .catch(error => console.error('Error:', error));
}

// Additional utility functions
function refreshPage() {
    // ✅ Complete page reload with cache-busting
    window.location.href = window.location.pathname + '?t=' + Date.now();
}

function showHelp() {
    alert(`Email Words Page Help:

• Use the search box to filter email addresses on the current page
• Click the copy button to copy individual email addresses
• Use "Copy All" to copy all visible email addresses
• Export button downloads the current page data as CSV
• Use pagination to navigate through all email words
• Click "Search in Files" to find where each email appears in documents

Keyboard Shortcuts:
• Ctrl+F: Focus search box
• Ctrl+A: Select all visible emails
• Ctrl+C: Copy selected emails`);
}

// Enhanced keyboard shortcuts
document.addEventListener('keydown', function(e) {
    if (e.ctrlKey && e.key === 'f') {
        e.preventDefault();
        document.getElementById('searchInput').focus();
    }
    if (e.ctrlKey && e.key === 'a' && e.target.tagName !== 'INPUT') {
        e.preventDefault();
        copyAllEmails();
    }
});

// Make functions globally available for onclick handlers in template
window.clearSearch = clearSearch;
window.copyEmail = copyEmail;
window.copyToClipboard = copyToClipboard;
window.searchInFiles = searchInFiles;
window.showEmailFiles = showEmailFiles;
window.exportData = exportData;
window.addToContacts = addToContacts;
window.refreshPage = refreshPage;
window.showHelp = showHelp;
window.sortTable = sortTable;
window.changePerPage = changePerPage;

// Export default initialization function for universal-initializer
export default function init() {
    // Initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initializeEmailWordsPage);
    } else {
        initializeEmailWordsPage();
    }
}