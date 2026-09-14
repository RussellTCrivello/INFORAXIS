/**
 * Base Page JavaScript - Handles common functionality for all pages
 * Extracted from base.html to keep HTML clean
 */

// Get current endpoint from data attribute or meta tag
function getCurrentEndpoint() {
    const body = document.body;
    const endpoint = body.getAttribute('data-current-endpoint') || 
                     body.getAttribute('data-endpoint') ||
                     (document.querySelector('meta[name="current-endpoint"]')?.getAttribute('content') || '');
    return endpoint;
}

// Get home URL from data attribute
function getHomeUrl() {
    const body = document.body;
    return body.getAttribute('data-home-url') || '/';
}

// Initialize base page functionality
document.addEventListener('DOMContentLoaded', function() {
    // Mobile menu toggle with backdrop
    const menuToggle = document.getElementById('menuToggle');
    const sidebar = document.getElementById('sidebar');
    const sidebarBackdrop = document.getElementById('sidebarBackdrop');
    
    function toggleSidebar() {
        if (sidebar) {
            const isOpen = sidebar.classList.contains('show');
            if (isOpen) {
                sidebar.classList.remove('show');
                if (sidebarBackdrop) {
                    sidebarBackdrop.classList.remove('show');
                }
                // Prevent body scroll when sidebar is open
                document.body.style.overflow = '';
            } else {
                sidebar.classList.add('show');
                if (sidebarBackdrop) {
                    sidebarBackdrop.classList.add('show');
                }
                // Prevent body scroll when sidebar is open
                document.body.style.overflow = 'hidden';
            }
        }
    }
    
    function closeSidebar() {
        if (sidebar) {
            sidebar.classList.remove('show');
            if (sidebarBackdrop) {
                sidebarBackdrop.classList.remove('show');
            }
            document.body.style.overflow = '';
        }
    }
    
    // Toggle sidebar on menu button click
    if (menuToggle && sidebar) {
        menuToggle.addEventListener('click', function(e) {
            e.stopPropagation();
            toggleSidebar();
        });
    }
    
    // Close sidebar when backdrop is clicked
    if (sidebarBackdrop) {
        sidebarBackdrop.addEventListener('click', function() {
            closeSidebar();
        });
    }
    
    // Close sidebar when clicking on a sidebar link (mobile)
    if (sidebar) {
        const sidebarLinks = sidebar.querySelectorAll('.sidebar-nav-link');
        sidebarLinks.forEach(link => {
            link.addEventListener('click', function() {
                // Only close on mobile/tablet
                if (window.innerWidth < 992) {
                    setTimeout(closeSidebar, 100); // Small delay for visual feedback
                }
            });
        });
    }
    
    // Close sidebar on window resize if it becomes desktop size
    let resizeTimeout;
    window.addEventListener('resize', function() {
        clearTimeout(resizeTimeout);
        resizeTimeout = setTimeout(function() {
            if (window.innerWidth >= 992 && sidebar) {
                closeSidebar();
            }
        }, 250);
    });
    
    // Close sidebar on Escape key
    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape' && sidebar && sidebar.classList.contains('show')) {
            closeSidebar();
        }
    });
    
    // Maintain sidebar active state
    function updateSidebarActiveState() {
        const currentPath = window.location.pathname;
        const currentEndpoint = getCurrentEndpoint();
        const sidebarLinks = document.querySelectorAll('.sidebar-nav-link:not(.language-switcher .sidebar-nav-link)');
        
        // Check if server already set an active state correctly
        const serverActiveLink = document.querySelector('.sidebar-nav-link.active:not(.language-switcher .sidebar-nav-link)');
        
        // If server set an active state and it matches current endpoint, trust it
        if (serverActiveLink && currentEndpoint) {
            const activeEndpoint = serverActiveLink.getAttribute('data-endpoint');
            if (activeEndpoint === currentEndpoint) {
                // Server state is correct, don't override
                return;
            }
        }
        
        // Otherwise, find and set the correct active state
        let foundActive = false;
        
        // Priority 1: Match by endpoint name (most reliable)
        if (currentEndpoint) {
            sidebarLinks.forEach(link => {
                const endpoint = link.getAttribute('data-endpoint');
                if (endpoint && endpoint === currentEndpoint) {
                    // Remove active from all other links
                    sidebarLinks.forEach(l => l.classList.remove('active'));
                    link.classList.add('active');
                    foundActive = true;
                }
            });
        }
        
        // Priority 2: Match by URL path (fallback)
        if (!foundActive) {
            sidebarLinks.forEach(link => {
                const href = link.getAttribute('href');
                if (href) {
                    try {
                        const hrefPath = new URL(href, window.location.origin).pathname;
                        if (currentPath === hrefPath || 
                            (hrefPath !== '/' && currentPath.startsWith(hrefPath + '/'))) {
                            // Remove active from all other links
                            sidebarLinks.forEach(l => l.classList.remove('active'));
                            link.classList.add('active');
                            foundActive = true;
                        }
                    } catch (e) {
                        // Try simple string matching
                        if (currentPath === href || (href !== '/' && currentPath.startsWith(href))) {
                            sidebarLinks.forEach(l => l.classList.remove('active'));
                            link.classList.add('active');
                            foundActive = true;
                        }
                    }
                }
            });
        }
    }
    
    // Immediately set clicked link as active and persist it
    const sidebarNav = document.querySelector('.sidebar-nav');
    if (sidebarNav) {
        sidebarNav.addEventListener('click', function(e) {
            const link = e.target.closest('.sidebar-nav-link');
            if (link && link.getAttribute('href') && !link.closest('.language-switcher')) {
                // Immediately set this link as active (visual feedback before navigation)
                const allLinks = document.querySelectorAll('.sidebar-nav-link:not(.language-switcher .sidebar-nav-link)');
                allLinks.forEach(l => l.classList.remove('active'));
                link.classList.add('active');
                
                // Store the clicked link's endpoint for after page reload
                const endpoint = link.getAttribute('data-endpoint');
                if (endpoint) {
                    sessionStorage.setItem('activeSidebarEndpoint', endpoint);
                }
            }
        });
    }
    
    // On page load, ensure the correct button is active
    window.addEventListener('load', function() {
        // First, let server-side template set active state
        // Then verify/update if needed
        setTimeout(function() {
            const storedEndpoint = sessionStorage.getItem('activeSidebarEndpoint');
            const currentEndpoint = getCurrentEndpoint();
            
            // If we have a stored endpoint and it matches current, ensure it's active
            if (storedEndpoint && storedEndpoint === currentEndpoint) {
                const sidebarLinks = document.querySelectorAll('.sidebar-nav-link:not(.language-switcher .sidebar-nav-link)');
                sidebarLinks.forEach(link => {
                    const endpoint = link.getAttribute('data-endpoint');
                    if (endpoint === storedEndpoint) {
                        sidebarLinks.forEach(l => l.classList.remove('active'));
                        link.classList.add('active');
                    }
                });
                // Clear stored state
                sessionStorage.removeItem('activeSidebarEndpoint');
            } else {
                // Update based on current endpoint/path
                updateSidebarActiveState();
            }
        }, 50);
    });
    
    // Also update on popstate (back/forward navigation)
    window.addEventListener('popstate', function() {
        setTimeout(updateSidebarActiveState, 50);
    });
    
    // Auto-hide alerts after 5 seconds
    // ALERT-01: only true flash messages auto-dismiss. The previous selector
    // closed every `.alert` on the page — including hidden error boxes inside
    // modals (removing form validation feedback) and the must-change-password
    // banner (removing its action button).
    const isFlashOnly = (alert) =>
        !alert.closest('.modal') &&
        !alert.classList.contains('d-none') &&
        !Array.from(alert.querySelectorAll('button, a, input, select, form'))
            .some(el => !el.classList.contains('btn-close'));
    const alerts = Array.from(document.querySelectorAll('.alert')).filter(isFlashOnly);
    if (alerts.length > 0) {
        alerts.forEach(alert => {
            setTimeout(() => {
                if (alert && alert.parentNode) {
                    const bsAlert = bootstrap.Alert.getOrCreateInstance(alert);
                    bsAlert.close();
                }
            }, 5000);
        });
    }
    
    // Smooth scroll for anchor links
    const anchorLinks = document.querySelectorAll('a[href^="#"]');
    if (anchorLinks.length > 0) {
        anchorLinks.forEach(anchor => {
            anchor.addEventListener('click', function (e) {
                e.preventDefault();
                const href = this.getAttribute('href');
                if (href && href !== '#') {
                    const target = document.querySelector(href);
                    if (target) {
                        target.scrollIntoView({
                            behavior: 'smooth',
                            block: 'start'
                        });
                    }
                }
            });
        });
    }
    
    // Initialize tooltips - only if Bootstrap is loaded
    if (typeof bootstrap !== 'undefined') {
        const tooltipTriggerList = document.querySelectorAll('[data-bs-toggle="tooltip"]');
        if (tooltipTriggerList.length > 0) {
            const tooltipList = Array.from(tooltipTriggerList).map(function (tooltipTriggerEl) {
                return new bootstrap.Tooltip(tooltipTriggerEl);
            });
        }
    }
    
    // Navigation Bar Functionality
    const navBackBtn = document.getElementById('navBackBtn');
    const navForwardBtn = document.getElementById('navForwardBtn');
    const navRefreshBtn = document.getElementById('navRefreshBtn');
    
    // Track navigation state
    let canGoBack = false;
    let canGoForward = false;
    
    // Check if we can navigate back/forward
    function updateNavigationButtons() {
        // Check if we can go back (if history.length > 1, we likely can)
        canGoBack = window.history.length > 1;
        canGoForward = false; // We can't reliably detect forward state
        
        // Try to detect if we came from another page
        if (document.referrer && document.referrer !== window.location.href) {
            canGoBack = true;
        }
    }
    
    // Enhanced back button with fallback
    if (navBackBtn) {
        navBackBtn.addEventListener('click', function(e) {
            e.preventDefault();
            if (document.referrer && document.referrer !== window.location.href) {
                window.history.back();
            } else {
                // Fallback: go to home page
                window.location.href = getHomeUrl();
            }
        });
    }
    
    // Enhanced forward button
    if (navForwardBtn) {
        navForwardBtn.addEventListener('click', function(e) {
            e.preventDefault();
            window.history.forward();
        });
    }
    
    // Enhanced refresh button with confirmation on forms
    if (navRefreshBtn) {
        navRefreshBtn.addEventListener('click', function(e) {
            // Check if there are unsaved form changes (basic check)
            const forms = document.querySelectorAll('form');
            let hasChanges = false;
            
            forms.forEach(form => {
                if (form.querySelector('input:not([type="hidden"]):not([readonly]), textarea:not([readonly]), select:not([readonly])')) {
                    hasChanges = true;
                }
            });
            
            if (hasChanges) {
                // Get refresh confirmation message from translations
                const refreshConfirmMsg = window.appTranslations?.['Are you sure you want to refresh? Unsaved changes may be lost.'] || 
                                         'Are you sure you want to refresh? Unsaved changes may be lost.';
                if (!confirm(refreshConfirmMsg)) {
                    return;
                }
            }
            
            location.reload();
        });
    }
    
    // Update on page load
    updateNavigationButtons();
    
    // Update on popstate (back/forward navigation) - debounced
    let popstateTimeout;
    window.addEventListener('popstate', function() {
        clearTimeout(popstateTimeout);
        popstateTimeout = setTimeout(updateNavigationButtons, 100);
    });
    
    // Keyboard shortcuts for navigation
    document.addEventListener('keydown', function(e) {
        // Alt+Left Arrow: Go back
        if (e.altKey && e.key === 'ArrowLeft' && !e.ctrlKey && !e.shiftKey) {
            e.preventDefault();
            if (navBackBtn) navBackBtn.click();
        }
        // Alt+Right Arrow: Go forward
        if (e.altKey && e.key === 'ArrowRight' && !e.ctrlKey && !e.shiftKey) {
            e.preventDefault();
            if (navForwardBtn) navForwardBtn.click();
        }
        // F5 or Ctrl+R: Refresh (with confirmation if needed)
        if ((e.key === 'F5') || (e.ctrlKey && e.key === 'r')) {
            // Allow default behavior, but our refresh button handler will catch it if needed
        }
    });
    
    // Language Switcher is now handled by LanguageSwitcher module
    // The module provides seamless AJAX-based language switching
});

