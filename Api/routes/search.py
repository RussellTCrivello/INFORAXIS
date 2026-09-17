"""
Search routes with enhanced full-text search, sorting, history, and saved searches.

This module provides:
- Full-text search using PostgreSQL tsvector/tsquery
- Sortable search results
- Search history tracking
- Saved searches management
- Export functionality
"""

from flask import render_template, request, jsonify, session, send_file
from Api.utils import (
    get_optimized_search_results, select_info_sources, select_info_sides,
    select_info_categories, search_files_by_word
)
from settings import get_settings
from Api.services.search_service import SearchService
from Api.services.search_history import SearchHistoryService, SavedSearchesService
from Api.services.export_service import ExportService
from Api.services.analyst_categories import AnalystCategoryService
from Api.routes.analyst_categories import resolve_request_scope
import logging
from datetime import datetime
from core.errors import client_error

logger = logging.getLogger(__name__)


from core.security.rate_limit import limiter


def _current_user_id():
    """AUDIT (API-04): the auth middleware stores the user id under
    ``session['auth_user_id']`` (core/security/flask_ext.py::_SESSION_USER_KEY);
    ``session['user_id']`` is never set, so search history and saved searches
    were always recorded with ``user_id = None`` and could not be scoped to,
    or cleaned up for, a user.
    """
    return session.get('auth_user_id')


def register_search_routes(app):
    """Register search routes with the Flask app"""
    
    @app.route('/search/enhanced')
    @limiter.limit("30 per minute")
    def search_enhanced_page():
        """Enhanced search page with full-text search, sorting, and filters"""
        from Api.utils import select_info_sources, select_info_sides, select_info_categories
        
        # Ensure all values are lists (handle None case)
        sources = select_info_sources() or []
        sides = select_info_sides() or []
        categories = select_info_categories() or []
        
        # Ensure they're iterable lists
        if not isinstance(sources, list):
            sources = list(sources) if sources else []
        if not isinstance(sides, list):
            sides = list(sides) if sides else []
        if not isinstance(categories, list):
            categories = list(categories) if categories else []
        
        return render_template('Search/search_enhanced.html',
                             sources=sources,
                             sides=sides,
                             categories=categories,
                             analyst_scope=resolve_request_scope())
    
    @app.route('/search')
    @limiter.limit("30 per minute")
    def search_page():
        """Enhanced Search with Content Filtering - Uses Google-like search algorithm"""
        settings = get_settings()
        search_config = settings.get_search_config()
        display_config = settings.get_display_config()
        
        query = request.args.get('q', '')
        page = request.args.get('page', 1, type=int)
        per_page = display_config.get('results_per_page', 10)
        max_results = search_config.get('max_results', 1000)
        results = []
        total_results = 0

        # Analyst-categorization search scope (FR-2.x): explicit parameter
        # wins and is persisted in the session (FR-2.3); otherwise the last
        # selection or the default "uncategorized only" (FR-2.1) applies.
        analyst_scope = resolve_request_scope()

        # Use Google-like search: supports multiple words, partial words, numbers
        # Minimum 2 chars (reduced from 3 to match enhanced search)
        if query and len(query.strip()) >= 2:
            # Use the enhanced search_files_by_word which now supports multiple words
            results, total_results = search_files_by_word(query, page, per_page, analyst_scope=analyst_scope)
            # Decorate results with analyst categories (own, separate
            # namespace - never merged with smart categories, FR-1.4)
            results = AnalystCategoryService.attach_categories_to_results(results)

        total_pages = (total_results + per_page - 1) // per_page if total_results > 0 else 1

        return render_template('Search/search.html',
                             query=query,
                             results=results,
                             page=page,
                             per_page=per_page,
                             total_pages=total_pages,
                             total_results=total_results,
                             analyst_scope=analyst_scope)
    
    @app.route('/search/saved')
    def saved_searches_page():
        """Saved Searches management page.

        FUNC-02: this template and its page script existed without a route.
        The saved-search CRUD endpoints (``/api/search/saved``) have always
        been live; this renders the management view over the same service.
        """
        searches = SavedSearchesService.get_saved_searches(user_id=_current_user_id()) or []
        return render_template('Search/saved_searches.html', saved_searches=searches)

    @app.route('/search/advanced')
    @limiter.limit("30 per minute")
    def search_advanced():
        """Advanced Search with Multiple Filters - Uses Google-like search algorithm"""
        # Get filter parameters
        file_type = request.args.get('file_type', '')
        source_id = request.args.get('source_id', '')
        side_id = request.args.get('side_id', '')
        date_from = request.args.get('date_from', '')
        date_to = request.args.get('date_to', '')
        query = request.args.get('q', '')

        # Analyst-categorization search scope (FR-2.x) - first-class input on
        # the Advanced Search interface (FR-3.2)
        analyst_scope = resolve_request_scope()
        
        results = []
        sources = select_info_sources() or []
        sides = select_info_sides() or []
        
        categories = select_info_categories() or []
        
        # Ensure they're iterable lists
        if not isinstance(sources, list):
            sources = list(sources) if sources else []
        if not isinstance(sides, list):
            sides = list(sides) if sides else []
        if not isinstance(categories, list):
            categories = list(categories) if categories else []
        
        settings = get_settings()
        search_config = settings.get_search_config()
        max_results = search_config.get('max_results', 1000)
        
        # Use Google-like search: supports multiple words, partial words, numbers
        # Minimum 2 chars to match enhanced search behavior
        if query or file_type or source_id or side_id or date_from or date_to:
            # Use optimized search function which now supports multiple words
            results = get_optimized_search_results(
                query=query if query and len(query.strip()) >= 2 else None,
                file_type=file_type,
                source_id=int(source_id) if source_id else None,
                side_id=int(side_id) if side_id else None,
                date_from=date_from,
                date_to=date_to,
                limit=min(100, max_results),  # Use settings max_results
                analyst_scope=analyst_scope
            )

        # Analyst categories for the manual-categorization control - a
        # dedicated namespace, never the smart category list (FR-1.4)
        analyst_categories = AnalystCategoryService.list_categories()

        return render_template('Search/search_advanced.html',
                             query=query,
                             file_type=file_type,
                             source_id=source_id,
                             side_id=side_id,
                             date_from=date_from,
                             date_to=date_to,
                             results=results,
                             sources=sources,
                             sides=sides,
                             categories=categories,
                             analyst_scope=analyst_scope,
                             analyst_categories=analyst_categories)
    
    @app.route('/search/advanced', methods=['POST'])
    @limiter.limit("30 per minute")
    def search_advanced_api():
        """Advanced Search API endpoint for JSON responses"""
        try:
            # Get search criteria from JSON request
            criteria = request.get_json()
            if not criteria:
                return jsonify({'error': 'No search criteria provided'}), 400
            
            # Extract search parameters
            query = criteria.get('query', '')
            file_type = criteria.get('file_type', '')
            source_id = criteria.get('source_id', '')
            side_id = criteria.get('side_id', '')
            date_from = criteria.get('date_from', '')
            date_to = criteria.get('date_to', '')
            category_id = criteria.get('category_id', '')

            # Analyst-categorization search scope (FR-2.x)
            analyst_scope = resolve_request_scope()

            settings = get_settings()
            search_config = settings.get_search_config()
            max_results = search_config.get('max_results', 1000)

            # Perform search using optimized search function (now supports multiple words)
            results = get_optimized_search_results(
                query=query if query and len(query.strip()) >= 2 else None,
                file_type=file_type,
                source_id=int(source_id) if source_id else None,
                side_id=int(side_id) if side_id else None,
                date_from=date_from,
                date_to=date_to,
                category_id=int(category_id) if category_id else None,
                limit=min(100, max_results),  # Use settings max_results
                analyst_scope=analyst_scope
            )
            
            # Format results for JSON response
            formatted_results = []
            for result in results:
                formatted_results.append({
                    'id': result[0],
                    'file_name': result[1],
                    'file_type': result[2],
                    'file_date': result[3].isoformat() if result[3] else None,
                    'source_name': result[4],
                    'side_name': result[5],
                    'file_status': result[6] if len(result) > 6 else 'Unknown'
                })
            
            return jsonify(formatted_results)
            
        except Exception as e:
            logger.error(f"Search API error: {e}")
            return client_error(e, subsystem='Api.routes.search', status=500)
    
    # ==================== ENHANCED SEARCH API ====================
    
    @app.route('/api/search', methods=['GET', 'POST'])
    @limiter.limit("30 per minute")
    def api_search():
        """
        Enhanced search API with full-text search, sorting, and filtering.
        
        Query Parameters (GET) or JSON Body (POST):
        - query: Search query string
        - file_type: Filter by file type
        - source_id: Filter by source ID
        - side_id: Filter by side ID
        - date_from: Start date (YYYY-MM-DD)
        - date_to: End date (YYYY-MM-DD)
        - category_id: Filter by category ID
        - sort_by: Sort field ('relevance', 'date', 'name', 'type', 'size')
        - sort_order: Sort order ('asc' or 'desc')
        - page: Page number (default: 1)
        - per_page: Results per page (default: 50)
        - use_fulltext: Use PostgreSQL full-text search (default: true)
        """
        try:
            # Get parameters from GET or POST
            if request.method == 'POST':
                data = request.get_json() or {}
                # Handle multiple values from JSON (arrays)
                source_ids = data.get('source_id') or data.get('source_ids', [])
                side_ids = data.get('side_id') or data.get('side_ids', [])
                category_ids = data.get('category_id') or data.get('category_ids', [])
                analyst_category_ids = data.get('analyst_category_id') or data.get('analyst_category_ids', [])
                file_type = data.get('file_type')
            else:
                # Handle GET parameters - use getlist for multiple values
                data = {}
                for key in request.args:
                    values = request.args.getlist(key)
                    if len(values) == 1:
                        data[key] = values[0]
                    else:
                        data[key] = values
                
                # Extract multiple values from query params
                source_ids = request.args.getlist('source_id')
                side_ids = request.args.getlist('side_id')
                category_ids = request.args.getlist('category_id')
                analyst_category_ids = request.args.getlist('analyst_category_id')
                file_type = request.args.getlist('file_type') if request.args.getlist('file_type') else data.get('file_type')
            
            query = data.get('query', '').strip()
            
            # Convert to lists of integers, handle both single and multiple values
            if source_ids:
                if isinstance(source_ids, (list, tuple)):
                    source_ids = [int(sid) for sid in source_ids if sid and str(sid).isdigit()]
                else:
                    try:
                        source_ids = [int(source_ids)]
                    except (ValueError, TypeError):
                        source_ids = []
            else:
                source_ids = []
            
            if side_ids:
                if isinstance(side_ids, (list, tuple)):
                    side_ids = [int(sid) for sid in side_ids if sid and str(sid).isdigit()]
                else:
                    try:
                        side_ids = [int(side_ids)]
                    except (ValueError, TypeError):
                        side_ids = []
            else:
                side_ids = []
            
            if category_ids:
                if isinstance(category_ids, (list, tuple)):
                    category_ids = [int(cid) for cid in category_ids if cid and str(cid).isdigit()]
                else:
                    try:
                        category_ids = [int(category_ids)]
                    except (ValueError, TypeError):
                        category_ids = []
            else:
                category_ids = []

            # Analyst (manual) category filter - parsed independently from
            # the smart category_ids above (FR-1.4 separation)
            if analyst_category_ids:
                if isinstance(analyst_category_ids, (list, tuple)):
                    analyst_category_ids = [int(cid) for cid in analyst_category_ids if cid and str(cid).isdigit()]
                else:
                    try:
                        analyst_category_ids = [int(analyst_category_ids)]
                    except (ValueError, TypeError):
                        analyst_category_ids = []
            else:
                analyst_category_ids = []
            
            # For backward compatibility, use first value if single selection
            source_id = source_ids[0] if source_ids else None
            side_id = side_ids[0] if side_ids else None
            category_id = category_ids[0] if category_ids else None
            
            date_from = data.get('date_from')
            date_to = data.get('date_to')
            sort_by = data.get('sort_by', 'relevance')
            sort_order = data.get('sort_order', 'desc')
            page = int(data.get('page', 1))
            per_page = min(int(data.get('per_page', 50)), 200)  # Max 200 per page
            use_fulltext = data.get('use_fulltext', 'true').lower() == 'true'
            use_advanced = data.get('use_advanced', 'true').lower() == 'true'  # Use advanced algorithms by default
            use_bm25 = data.get('use_bm25', 'true').lower() == 'true'
            use_expansion = data.get('use_expansion', 'true').lower() == 'true'
            use_fuzzy = data.get('use_fuzzy', 'true').lower() == 'true'
            
            offset = (page - 1) * per_page

            # Analyst-categorization search scope (FR-2.x): explicit
            # parameter wins and is session-persisted (FR-2.3); default is
            # "uncategorized files only" (FR-2.1). Applies to every search
            # path below and filters strictly on analyst categorization
            # status - smart categorization is never consulted (FR-2.4).
            analyst_scope = resolve_request_scope()

            # Perform search - use advanced search if enabled
            if use_advanced and query:
                results, total_count = SearchService.advanced_search(
                    query=query,
                    file_type=file_type,
                    source_id=source_id,
                    side_id=side_id,
                    date_from=date_from,
                    date_to=date_to,
                    category_id=category_id,
                    source_ids=source_ids if source_ids else None,
                    side_ids=side_ids if side_ids else None,
                    category_ids=category_ids if category_ids else None,
                    sort_by=sort_by,
                    sort_order=sort_order,
                    limit=per_page,
                    offset=offset,
                    use_bm25=use_bm25,
                    use_expansion=use_expansion,
                    use_fuzzy=use_fuzzy,
                    analyst_scope=analyst_scope,
                    analyst_category_ids=analyst_category_ids if analyst_category_ids else None
                )
            elif use_fulltext and query:
                results, total_count = SearchService.full_text_search(
                    query=query,
                    file_type=file_type,
                    source_id=source_id,
                    side_id=side_id,
                    date_from=date_from,
                    date_to=date_to,
                    category_id=category_id,
                    sort_by=sort_by,
                    sort_order=sort_order,
                    limit=per_page,
                    offset=offset,
                    analyst_scope=analyst_scope
                )
            else:
                # Fallback to simple search
                if query:
                    results, total_count = SearchService.simple_search(
                        query=query,
                        limit=per_page,
                        offset=offset,
                        analyst_scope=analyst_scope
                    )
                else:
                    results, total_count = [], 0

            # Decorate results with analyst categories in their own field -
            # visually and structurally separate from any smart-category
            # field on the same result (FR-1.4).
            results = AnalystCategoryService.attach_categories_to_results(results)
            
            # Save to search history
            if query:
                user_id = _current_user_id()
                SearchHistoryService.add_search(
                    query=query,
                    filters={
                        'file_type': file_type,
                        'source_id': source_id,
                        'side_id': side_id,
                        'date_from': date_from,
                        'date_to': date_to,
                        'category_id': category_id,
                        'analyst_scope': analyst_scope
                    },
                    result_count=total_count,
                    user_id=user_id
                )
            
            total_pages = (total_count + per_page - 1) // per_page if total_count > 0 else 1
            
            return jsonify({
                'results': results,
                'pagination': {
                    'page': page,
                    'per_page': per_page,
                    'total': total_count,
                    'total_pages': total_pages,
                    'has_prev': page > 1,
                    'has_next': page < total_pages
                },
                'query': query,
                'filters': {
                    'file_type': file_type,
                    'source_id': source_id,
                    'side_id': side_id,
                    'date_from': date_from,
                    'date_to': date_to,
                    'category_id': category_id,
                    # Analyst-categorization scope actually applied (FR-2.x)
                    'analyst_scope': analyst_scope
                },
                'sort': {
                    'by': sort_by,
                    'order': sort_order
                }
            })
            
        except Exception as e:
            logger.error(f"Enhanced search API error: {e}", exc_info=True)
            return client_error(e, subsystem='Api.routes.search', status=500)
    
    # ==================== AUTOCOMPLETE / SUGGESTIONS ====================
    
    @app.route('/api/search/autocomplete', methods=['GET'])
    def api_autocomplete():
        """
        Get autocomplete suggestions for a search query.
        
        Query Parameters:
        - query: Partial query string (required)
        - limit: Maximum number of suggestions (default: 10)
        """
        try:
            query = request.args.get('query', '').strip()
            limit = int(request.args.get('limit', 10))
            
            if not query or len(query) < 2:
                return jsonify({
                    'suggestions': [],
                    'count': 0
                })
            
            suggestions = SearchService.autocomplete(query, limit=limit)
            
            return jsonify({
                'suggestions': suggestions,
                'count': len(suggestions),
                'query': query
            })
            
        except Exception as e:
            logger.error(f"Autocomplete API error: {e}", exc_info=True)
            return client_error(e, subsystem='Api.routes.search', status=500)
    
    @app.route('/api/search/suggestions', methods=['GET'])
    def api_suggestions():
        """
        Get simple search suggestions (just text strings).
        
        Query Parameters:
        - query: Partial query string (required)
        - limit: Maximum number of suggestions (default: 5)
        """
        try:
            query = request.args.get('query', '').strip()
            limit = int(request.args.get('limit', 5))
            
            if not query or len(query) < 2:
                return jsonify({
                    'suggestions': []
                })
            
            suggestions = SearchService.get_search_suggestions(query, limit=limit)
            
            return jsonify({
                'suggestions': suggestions
            })
            
        except Exception as e:
            logger.error(f"Suggestions API error: {e}", exc_info=True)
            return client_error(e, subsystem='Api.routes.search', status=500)
    
    # ==================== SEARCH HISTORY ====================
    
    @app.route('/api/search/history', methods=['GET', 'POST'])
    def api_search_history():
        """
        Get or add search history.
        
        GET:
        - limit: Maximum number of entries (default: 20)
        
        POST:
        - query: Search query string
        - filters: Optional search filters dictionary
        - result_count: Optional number of results
        """
        try:
            if request.method == 'POST':
                # Add search to history
                data = request.get_json() or {}
                query = data.get('query', '').strip()
                filters = data.get('filters', {})
                result_count = data.get('result_count', 0)
                user_id = _current_user_id()
                
                if query:
                    SearchHistoryService.add_search(
                        query=query,
                        filters=filters,
                        result_count=result_count,
                        user_id=user_id
                    )
                    return jsonify({
                        'success': True,
                        'message': 'Search added to history'
                    }), 201
                else:
                    return jsonify({
                        'success': False,
                        'error': 'Query is required'
                    }), 400
            else:
                # GET - retrieve search history
                limit = int(request.args.get('limit', 20))
                user_id = _current_user_id()
                
                history = SearchHistoryService.get_history(limit=limit, user_id=user_id)
                
                return jsonify({
                    'history': history,
                    'count': len(history)
                })
            
        except Exception as e:
            logger.error(f"Search history API error: {e}", exc_info=True)
            return client_error(e, subsystem='Api.routes.search', status=500)
    
    @app.route('/api/search/history', methods=['DELETE'])
    def api_clear_search_history():
        """Clear search history."""
        try:
            user_id = _current_user_id()
            SearchHistoryService.clear_history(user_id=user_id)
            
            return jsonify({'success': True, 'message': 'Search history cleared'})
            
        except Exception as e:
            logger.error(f"Clear search history error: {e}", exc_info=True)
            return client_error(e, subsystem='Api.routes.search', status=500)
    
    # ==================== SAVED SEARCHES ====================
    
    @app.route('/api/search/saved', methods=['GET'])
    def api_get_saved_searches():
        """Get all saved searches."""
        try:
            user_id = _current_user_id()
            searches = SavedSearchesService.get_saved_searches(user_id=user_id)
            
            return jsonify({
                'searches': searches,
                'count': len(searches)
            })
            
        except Exception as e:
            logger.error(f"Get saved searches error: {e}", exc_info=True)
            return client_error(e, subsystem='Api.routes.search', status=500)
    
    @app.route('/api/search/saved', methods=['POST'])
    def api_save_search():
        """
        Save a search.
        
        JSON Body:
        - name: Name for the saved search
        - query: Search query string
        - filters: Optional search filters dictionary
        """
        try:
            data = request.get_json()
            if not data:
                return jsonify({'error': 'No data provided'}), 400
            
            name = data.get('name', '').strip()
            query = data.get('query', '').strip()
            filters = data.get('filters', {})
            
            if not name:
                return jsonify({'error': 'Name is required'}), 400
            
            user_id = _current_user_id()
            search_id = SavedSearchesService.save_search(
                name=name,
                query=query,
                filters=filters,
                user_id=user_id
            )
            
            return jsonify({
                'success': True,
                'search_id': search_id,
                'message': 'Search saved successfully'
            }), 201
            
        except Exception as e:
            logger.error(f"Save search error: {e}", exc_info=True)
            return client_error(e, subsystem='Api.routes.search', status=500)
    
    @app.route('/api/search/saved/<int:search_id>', methods=['GET'])
    def api_get_saved_search(search_id):
        """Get a specific saved search."""
        try:
            search = SavedSearchesService.get_saved_search(search_id)
            
            if not search:
                return jsonify({'error': 'Saved search not found'}), 404
            
            # Mark as used
            SavedSearchesService.mark_used(search_id)
            
            return jsonify({'search': search})
            
        except Exception as e:
            logger.error(f"Get saved search error: {e}", exc_info=True)
            return client_error(e, subsystem='Api.routes.search', status=500)
    
    @app.route('/api/search/saved/<int:search_id>', methods=['PUT'])
    def api_update_saved_search(search_id):
        """
        Update a saved search.
        
        JSON Body (all optional):
        - name: New name
        - query: New query
        - filters: New filters
        """
        try:
            data = request.get_json() or {}
            
            success = SavedSearchesService.update_saved_search(
                search_id=search_id,
                name=data.get('name'),
                query=data.get('query'),
                filters=data.get('filters')
            )
            
            if not success:
                return jsonify({'error': 'Saved search not found'}), 404
            
            return jsonify({
                'success': True,
                'message': 'Search updated successfully'
            })
            
        except Exception as e:
            logger.error(f"Update saved search error: {e}", exc_info=True)
            return client_error(e, subsystem='Api.routes.search', status=500)
    
    @app.route('/api/search/saved/<int:search_id>', methods=['DELETE'])
    def api_delete_saved_search(search_id):
        """Delete a saved search."""
        try:
            success = SavedSearchesService.delete_saved_search(search_id)
            
            if not success:
                return jsonify({'error': 'Saved search not found'}), 404
            
            return jsonify({
                'success': True,
                'message': 'Search deleted successfully'
            })
            
        except Exception as e:
            logger.error(f"Delete saved search error: {e}", exc_info=True)
            return client_error(e, subsystem='Api.routes.search', status=500)
    
    # ==================== EXPORT SEARCH RESULTS ====================
    
    @app.route('/api/search/export', methods=['POST'])
    def api_export_search_results():
        """
        Export search results to CSV, Excel, or JSON.
        
        JSON Body:
        - results: List of search result dictionaries
        - format: Export format ('csv', 'excel', 'json')
        - filename: Optional filename
        """
        try:
            data = request.get_json()
            if not data:
                return jsonify({'error': 'No data provided'}), 400
            
            results = data.get('results', [])
            export_format = data.get('format', 'csv').lower()
            filename = data.get('filename', f'search_results_{datetime.now().strftime("%Y%m%d_%H%M%S")}')
            
            if not results:
                return jsonify({'error': 'No results to export'}), 400
            
            # Convert results to list of dictionaries if needed
            if results and isinstance(results[0], (list, tuple)):
                # Convert tuple results to dictionaries
                formatted_results = []
                for result in results:
                    if isinstance(result, (list, tuple)):
                        formatted_results.append({
                            'id': result[0] if len(result) > 0 else None,
                            'file_name': result[1] if len(result) > 1 else None,
                            'file_type': result[2] if len(result) > 2 else None,
                            'file_date': result[3].isoformat() if len(result) > 3 and result[3] else None,
                            'source_name': result[4] if len(result) > 4 else None,
                            'side_name': result[5] if len(result) > 5 else None,
                            'file_status': result[6] if len(result) > 6 else None
                        })
                    else:
                        formatted_results.append(result)
                results = formatted_results
            
            # Export based on format
            if export_format == 'csv':
                export_data = ExportService.export_search_results_csv(results)
                mimetype = 'text/csv'
                extension = 'csv'
            elif export_format == 'excel':
                export_data = ExportService.export_search_results_excel(results)
                mimetype = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
                extension = 'xlsx'
            elif export_format == 'json':
                export_data = ExportService.export_search_results_json(results)
                mimetype = 'application/json'
                extension = 'json'
            else:
                return jsonify({'error': f'Unsupported format: {export_format}'}), 400
            
            return send_file(
                export_data,
                mimetype=mimetype,
                as_attachment=True,
                download_name=f'{filename}.{extension}'
            )
            
        except Exception as e:
            logger.error(f"Export search results error: {e}", exc_info=True)
            return client_error(e, subsystem='Api.routes.search', status=500)

