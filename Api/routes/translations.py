"""
Translation API Routes
Provides centralized translation management for the frontend
"""

from flask import Blueprint, jsonify, request, current_app
from flask_babel import get_locale, _
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

translations_bp = Blueprint('translations', __name__)


def get_all_translations(locale: str = None) -> dict:
    """
    Get all translations for a given locale
    
    Args:
        locale: Language code (e.g., 'en', 'ar'). If None, uses current locale.
    
    Returns:
        Dictionary of all translations
    """
    if locale is None:
        try:
            locale = str(get_locale())
        except Exception:
            locale = 'en'
    
    translations = {}
    
    try:
        # Load translations from Babel message files
        from flask_babel import get_translations
        import babel.support
        
        # Get Flask-Babel translations for the requested locale
        with current_app.app_context():
            # Force locale if specified
            if locale:
                from flask import g
                g.locale = locale
            
            translations_obj = get_translations()
            
            if translations_obj and hasattr(translations_obj, '_catalog'):
                # Extract all message IDs and their translations
                catalog = translations_obj._catalog
                for message_id, message_string in catalog.items():
                    if message_id and message_id != '':
                        # Use the translated string, or fallback to message_id
                        if message_string:
                            translations[message_id] = message_string
                        else:
                            translations[message_id] = message_id
            
            # Also try to load from .po files directly
            try:
                translations_dir = Path(current_app.root_path).parent / 'translations' / locale / 'LC_MESSAGES'
                po_file = translations_dir / 'messages.po'
                
                if po_file.exists():
                    from babel.messages import catalog as babel_catalog
                    from babel.messages.pofile import read_po
                    
                    with open(po_file, 'rb') as f:
                        catalog = read_po(f, locale=locale)
                        
                        for message in catalog:
                            if message.id and message.id != '':
                                if message.string:
                                    translations[message.id] = message.string
                                else:
                                    translations[message.id] = message.id
            except Exception as e:
                logger.debug(f"Could not load from .po file: {e}")
        
        # Also load from config.json if available
        config_path = Path(current_app.root_path).parent / 'config.json'
        if config_path.exists():
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    # Add any translation-related config
                    if 'translations' in config:
                        translations.update(config['translations'].get(locale, {}))
            except Exception as e:
                logger.debug(f"Could not load translations from config: {e}")
        
    except Exception as e:
        logger.error(f"Error loading translations for locale {locale}: {e}")
    
    return translations


@translations_bp.route('/api/i18n/catalog', methods=['GET'])
def get_i18n_catalog():
    """Public, read-only client localization catalog.

    Returns *only* the Babel message catalog (UI strings) for the requested
    locale. Unlike /api/translations it never touches configuration files, so
    it is safe to expose to every user - the client i18n runtime
    (static/js/modules/core/app-i18n.js) needs this catalog to translate
    JavaScript-rendered interfaces for non-admin users as well.
    """
    try:
        locale = request.args.get('locale')
        if not locale:
            try:
                locale = str(get_locale())
            except Exception:
                locale = 'en'
        # Only serve locales the application actually knows about.
        known = current_app.config.get('LANGUAGES', {})
        if locale not in known:
            # Accept a base-language match (e.g. 'ar-EG' -> 'ar').
            base = str(locale).split('-')[0]
            locale = base if base in known else 'en'

        translations = {}
        try:
            # Resolve the project root by walking up from the app package
            # (root_path is <project>/apps/web) until the translations dir.
            project_root = Path(current_app.root_path)
            translations_dir = None
            for _ in range(4):
                candidate = project_root / 'translations' / locale / 'LC_MESSAGES'
                if candidate.is_dir():
                    translations_dir = candidate
                    break
                project_root = project_root.parent
            po_file = translations_dir / 'messages.po' if translations_dir else None
            if po_file and po_file.exists():
                from babel.messages.pofile import read_po
                with open(po_file, 'rb') as f:
                    catalog = read_po(f, locale=locale)
                    for message in catalog:
                        if message.id and message.string:
                            translations[message.id] = message.string
        except Exception as e:
            logger.debug(f"Could not load i18n catalog for {locale}: {e}")

        return jsonify({
            'success': True,
            'locale': locale,
            'count': len(translations),
            'translations': translations
        })
    except Exception as e:
        logger.error(f"Error building i18n catalog: {e}")
        return jsonify({
            'success': False,
            'locale': 'en',
            'translations': {}
        }), 200


@translations_bp.route('/api/translations', methods=['GET'])
def get_translations():
    """API endpoint to get all translations for current locale"""
    try:
        locale = request.args.get('locale')
        if not locale:
            try:
                locale = str(get_locale())
            except Exception:
                locale = 'en'
        
        translations = get_all_translations(locale)
        
        return jsonify({
            'success': True,
            'locale': locale,
            'translations': translations
        })
    except Exception as e:
        logger.error(f"Error getting translations: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@translations_bp.route('/api/translations/locale', methods=['GET'])
def get_current_locale():
    """API endpoint to get current locale"""
    try:
        locale = str(get_locale())
        return jsonify({
            'success': True,
            'locale': locale
        })
    except Exception:
        return jsonify({
            'success': True,
            'locale': 'en'
        })


@translations_bp.route('/api/translations/available', methods=['GET'])
def get_available_locales():
    """API endpoint to get list of available locales"""
    try:
        languages = current_app.config.get('LANGUAGES', {})
        return jsonify({
            'success': True,
            'locales': list(languages.keys()),
            'languages': languages
        })
    except Exception as e:
        logger.error(f"Error getting available locales: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
            'locales': ['en'],
            'languages': {'en': 'English'}
        })


def register_translation_routes(app):
    """Register translation routes with the Flask app"""
    app.register_blueprint(translations_bp)
    logger.info("✅ Translation API routes registered")

