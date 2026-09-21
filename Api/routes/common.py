"""
Common routes (language, context processor, etc.)
"""

from flask import redirect, url_for, flash, session, request, g
from flask_babel import Babel, gettext as _
from datetime import datetime, date
import time
import logging

logger = logging.getLogger(__name__)


def register_common_routes(app, babel_instance):
    """Register common routes and context processors with the Flask app"""
    
    def get_locale():
        """Get the locale/language from session (user choice), system settings, or browser preference"""
        # PRIORITY 1: Check session first (user's explicit choice takes precedence)
        # This ensures that when user switches language, it doesn't get overridden
        if 'language' in session:
            session_lang = session.get('language')
            if session_lang and session_lang in app.config['LANGUAGES']:
                return session_lang

        # PRIORITY 1.5: Explicit user preference carried in the user_language
        # cookie (set by the login-screen language switcher for anonymous
        # visitors). Session priority still wins once the user signs in.
        cookie_lang = request.cookies.get('user_language')
        if cookie_lang and cookie_lang in app.config['LANGUAGES']:
            return cookie_lang
        
        # PRIORITY 2: Check system settings (persistent across restarts)
        if 'SETTINGS' in app.config and app.config['SETTINGS']:
            try:
                system_config = app.config['SETTINGS'].get_system_config()
                system_language = system_config.get('language', 'en')
                if system_language in app.config['LANGUAGES']:
                    # Sync session with system setting for consistency (only if session not set)
                    if 'language' not in session:
                        session['language'] = system_language
                    return system_language
            except Exception:
                pass  # Fall through to browser preference
        
        # PRIORITY 3: Check browser's Accept-Language header (but only if no explicit choice)
        browser_lang = request.accept_languages.best_match(app.config['LANGUAGES'].keys())
        if browser_lang:
            # Only use browser language if session doesn't have an explicit choice
            if 'language' not in session:
                return browser_lang
        
        # PRIORITY 4: Default fallback
        return app.config['BABEL_DEFAULT_LOCALE']
    
    @app.route('/set_language/<language>')
    def set_language(language):
        """Route to switch language - SYSTEM-WIDE"""
        if language in app.config['LANGUAGES']:
            # Update session FIRST (this ensures get_locale() will use session priority)
            session['language'] = language
            try:
                from settings import get_settings
                settings = get_settings()
                # Use dot notation for unified settings
                settings.set_setting('system.language', language)
                # Update app config
                app.config['BABEL_DEFAULT_LOCALE'] = language
                if 'SETTINGS' in app.config and app.config['SETTINGS']:
                    app.config['SETTINGS'].system.language = language
                    # Force reload to clear cache
                    app.config['SETTINGS'].reload_from_file()
                logger.info(f"✅ Language updated system-wide via /set_language: {language} (session updated first)")
            except Exception as e:
                logger.warning(f"Could not update system settings for language: {e}")
            
            # Force locale immediately for this request
            if babel_instance:
                from flask_babel import force_locale
                with force_locale(language):
                    flash(_('Language changed to %(lang)s', lang=app.config["LANGUAGES"][language]), 'info')
            else:
                flash(_('Language changed to %(lang)s', lang=app.config["LANGUAGES"][language]), 'info')
        
        # Support AJAX requests
        if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            from flask import jsonify
            return jsonify({
                'success': True,
                'language': language,
                'language_name': app.config['LANGUAGES'].get(language, language),
                'message': _('Language changed to %(lang)s', lang=app.config["LANGUAGES"].get(language, language))
            })
        
        return redirect(request.referrer or url_for('index'))
    
    @app.context_processor
    def inject_now():
        """Inject datetime functions and translation helper into templates"""
        from flask_wtf.csrf import generate_csrf
        
        # Import centralized version
        try:
            from version import get_version
            app_version = get_version()
        except ImportError:
            app_version = "2.0.0"
        
        context = {
            'now': datetime.now,
            'datetime': datetime,
            'date': date,
            '_': _,  # Translation function
            'get_locale': get_locale,
            'languages': app.config.get('LANGUAGES', {}),
            'current_language': get_locale(),
            'csrf_token': generate_csrf,  # CSRF token function for templates
            'version': app_version,  # Application version
        }
        
        # Safely inject interface manager - wrap in try-except to prevent cascading errors
        try:
            from settings import get_interface_manager
            interface_manager = get_interface_manager()
            context['interface_manager'] = interface_manager
            context['is_interface_enabled'] = interface_manager.is_interface_enabled
            context['is_interface_enabled_by_endpoint'] = interface_manager.is_interface_enabled_by_endpoint
            # Also inject as user_settings for template compatibility
            context['user_settings'] = interface_manager

            # The registry itself, so a template asks the product model rather
            # than a copied list: what exists, what it is called, where it
            # lives and who should see it.
            from core.interfaces import get_interface, get_interfaces_by_domain
            interface_state = interface_manager.get_state()
            context['interface_state'] = interface_state
            context['interface_registry'] = get_interface
            context['interfaces_by_domain'] = get_interfaces_by_domain()
            # Navigation data: the interfaces this user may actually see,
            # grouped by domain - the shell renders from this instead of
            # repeating the product map in markup.
            try:
                from core.interfaces import DOMAIN_LABELS
                context['domain_labels'] = {str(d): label for d, label in DOMAIN_LABELS.items()}

                current_user_obj = getattr(g, 'user', None)
                # No session means no navigation: the sidebar is a list of what
                # this operator may open, and an anonymous visitor may open
                # nothing that requires a session.
                if current_user_obj is None or not getattr(current_user_obj, 'is_authenticated', False):
                    context['nav_interfaces'] = {}
                else:
                    context['nav_interfaces'] = interface_state.get_visible_by_domain(current_user_obj)
            except Exception as e:
                logger.debug("Navigation could not be built from the registry: %s", e)
                context['nav_interfaces'] = {}
        except Exception as e:
            logger.warning(f"Failed to load interface manager in context processor: {e}")
            # The registry is what decides whether an interface exists, so a
            # failure here must not become "everything is enabled": templates
            # get the strict answers (nothing is enabled, nothing is visible)
            # and the page renders its empty state rather than claiming a
            # product surface that could not be verified.
            context['interface_manager'] = None
            context['user_settings'] = None
            context['interface_state'] = None
            context['interface_registry'] = lambda interface_id: None
            context['interfaces_by_domain'] = {}
            context['domain_labels'] = {}
            context['nav_interfaces'] = {}
            context['is_interface_enabled'] = lambda interface_id: False
            context['is_interface_enabled_by_endpoint'] = lambda endpoint: False
        
        return context
    
    @app.before_request
    def before_request():
        """Track request start time for profiling, ensure locale is set, and check interface access"""
        g.start_time = time.time()
        
        # Check interface access - block disabled interfaces
        # Skip check for static files, API endpoints, setup, and settings page (always accessible)
        # Settings page must always be accessible so users can re-enable interfaces
        #
        # OPS-05b: 'index' (the dashboard / home page) is exempt. The gate
        # redirects a blocked endpoint to url_for('index'); if the index is
        # itself subject to the gate and reads as disabled, that redirects to
        # itself and the browser reports ERR_TOO_MANY_REDIRECTS, leaving the
        # application unusable with no way back into Settings to re-enable
        # anything. The home page must therefore never be gated.
        from core.interfaces import SYSTEM_ENDPOINTS, is_infrastructure_endpoint

        endpoint = request.endpoint
        settings_endpoint = bool(endpoint) and endpoint.startswith(('settings_page', 'settings_api.'))
        infrastructure = is_infrastructure_endpoint(endpoint, request.path)

        if (endpoint and endpoint != 'static' and endpoint != 'index'
                and not infrastructure
                and endpoint not in SYSTEM_ENDPOINTS
                and not settings_endpoint
                and not request.path.startswith('/static')
                and not request.path.startswith('/settings')):

            try:
                from settings import get_interface_manager
                interface_manager = get_interface_manager()

                # The interface that owns this endpoint decides whether it is
                # served. An endpoint no interface owns is refused: the old
                # behaviour ("not in the map, therefore enabled") made an
                # unregistered page indistinguishable from a registered one,
                # which is exactly the gap the registry exists to close.
                if not interface_manager.is_interface_enabled_by_endpoint(endpoint):
                    logger.info("Access denied to disabled or unregistered endpoint: %s", endpoint)
                    flash(_('This section is currently disabled. Please enable it in Settings to access.'), 'warning')
                    return redirect(url_for('index'))
            except Exception as check_error:
                # A check that could not run is not permission to proceed.
                #
                # This used to log at debug level and serve the page anyway,
                # which meant a broken interface state was indistinguishable
                # from a working one: the operator saw a normal page and no
                # indication that the product's own gate had failed. The error
                # now goes through the common pipeline (correlation id, details
                # server-side only, generic message to the browser), and the
                # dashboard and Settings stay exempt so the failure can be
                # inspected and repaired.
                logger.warning(
                    "Interface access check failed for endpoint %s: %s",
                    endpoint, check_error,
                )
                raise

        # CRITICAL: Prioritize session language if it exists (user's explicit choice)
        # Handle X-Language header with explicit flag
        request_lang = request.headers.get('X-Language')
        is_explicit = request.headers.get('X-Language-Explicit') == 'true'
        
        # Check if session already has a language (user's explicit choice takes priority)
        if 'language' in session and session.get('language') in app.config['LANGUAGES']:
            session_lang = session.get('language')
            
            # If request explicitly says user set this language, and it differs from session,
            # update session to match (user just changed language)
            if is_explicit and request_lang and request_lang in app.config['LANGUAGES']:
                if request_lang != session_lang:
                    logger.info(f"User explicitly changed language from {session_lang} to {request_lang}, updating session")
                    session['language'] = request_lang
                    session.permanent = True
                    locale = request_lang
                else:
                    locale = session_lang
            else:
                # Session has language - use it (don't let request header override unless explicit)
                locale = session_lang
                # If request header differs and is not explicit, log it but don't change
                if request_lang and request_lang != locale and not is_explicit:
                    logger.debug(f"Request header language ({request_lang}) differs from session ({locale}), using session")
        elif request_lang and request_lang in app.config['LANGUAGES']:
            # No session language, but request has one - use it and save to session
            session['language'] = request_lang
            session.permanent = True
            locale = request_lang
            if is_explicit:
                logger.info(f"Setting language from explicit request: {request_lang}")
        else:
            # No header, no session - use get_locale() which checks system settings and browser
            locale = get_locale()  # This will check session first, then system settings
            if locale and locale in app.config['LANGUAGES']:
                # Sync session if it's not already set
                if 'language' not in session:
                    session['language'] = locale
                    session.permanent = True  # Make session persistent
                elif session.get('language') != locale:
                    # If session has a different language, trust the session (user's explicit choice)
                    locale = session.get('language')
        
        if locale and locale in app.config['LANGUAGES']:
            # Store locale in g for use in templates and Babel
            g.locale = locale
            
            # Ensure Babel uses the correct locale for this request
            if babel_instance:
                from flask_babel import force_locale
                # Force locale for this request context
                g._babel_locale = locale
        
        # Check for settings file changes periodically (every 10th request to avoid overhead)
        # This allows external modifications to settings.json to be picked up
        if not hasattr(g, '_settings_check_count'):
            g._settings_check_count = 0
        g._settings_check_count += 1
        
        if g._settings_check_count % 10 == 0:  # Check every 10 requests
            try:
                from settings import reload_settings_from_file, get_settings
                if reload_settings_from_file():
                    settings = get_settings()
                    # Update app config if language/timezone changed
                    system_config = settings.get_system_config()
                    if 'BABEL_DEFAULT_LOCALE' in app.config:
                        app.config['BABEL_DEFAULT_LOCALE'] = system_config.get('language', 'en')
                    if 'BABEL_DEFAULT_TIMEZONE' in app.config:
                        app.config['BABEL_DEFAULT_TIMEZONE'] = system_config.get('timezone', 'UTC')
                    logger.info("✅ Settings reloaded from file during request")
            except Exception as e:
                # Don't fail requests if settings reload fails
                logger.debug(f"Settings reload check failed: {e}")
    
    @app.after_request
    def after_request(response):
        """Set language header in response and log slow endpoints"""
        # Set response header to communicate language back to client
        if hasattr(g, 'locale') and g.locale:
            response.headers['X-Language'] = g.locale
        
        # Log slow endpoints
        if hasattr(g, 'start_time'):
            elapsed = time.time() - g.start_time
            if elapsed > 2.0:  # Log requests taking > 2 seconds
                logger.warning(f"⚠️ SLOW ENDPOINT ({elapsed:.2f}s): {request.method} {request.path}")
        
        return response
    
    
    @app.template_filter('format_date')
    def format_date_filter(value, format_string='%Y-%m-%d'):
        """
        Format a date/datetime value, handling both datetime objects and strings.
        
        Args:
            value: datetime, date, or string value
            format_string: strftime format string (default: '%Y-%m-%d')
        
        Returns:
            Formatted date string or 'N/A' if value is None or invalid
        """
        if value is None:
            return 'N/A'
        
        try:
            # If it's already a datetime or date object, use strftime
            if hasattr(value, 'strftime'):
                return value.strftime(format_string)
            
            # If it's a string, try to parse it
            if isinstance(value, str):
                # Try common date formats
                from datetime import datetime
                for fmt in ['%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%Y-%m-%d', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%dT%H:%M:%S.%f']:
                    try:
                        dt = datetime.strptime(value, fmt)
                        return dt.strftime(format_string)
                    except ValueError:
                        continue
                # If parsing fails, return the string as-is (might already be formatted)
                return value
            
            # For any other type, try to convert to string
            return str(value)
        except Exception as e:
            logger.warning(f"Error formatting date {value}: {e}")
            return 'N/A'
    
    @app.template_filter('number_format')
    def number_format(value):
        """
        Format number with thousand separators.
        
        Args:
            value: Number to format
            
        Returns:
            Formatted string with commas or original value if invalid
        """
        try:
            return f"{int(value):,}"
        except (ValueError, TypeError):
            return value

