"""
Archives routes
"""

from flask import render_template, request, jsonify, flash, make_response
from Api.utils import (
    execute_query, load_text_keyword, load_text_title,
    select_info_sources, select_info_sides, get_categories_with_stats,
    get_archive_statistics
)
import logging
from core.serialization import pack_int_list, unpack_int_list
from core.errors import client_error

logger = logging.getLogger(__name__)


def register_archives_routes(app):
    """Register archives routes with the Flask app"""
    
    @app.route('/archives')
    def archives_page():
        """Archives page displaying categories, keywords, titles, sources, sides, and hashs"""
        try:
            categories_data = get_categories_with_stats(limit=100)
            
            categories = []
            for cat in categories_data:
                file_count = cat.get('file_count') or 0
                # Only include categories that have files
                if file_count > 0:
                    categories.append({
                        'id': cat.get('id'),
                        'name': cat.get('name') or 'Unnamed Category',
                        'file_count': file_count,
                        'word_count': cat.get('word_count') or 0
                    })

            keywords_data = execute_query("""
                SELECT k.id, k.category_id, k.keyword,
                       COUNT(DISTINCT kp.path_id) as file_count
                FROM keywords k
                LEFT JOIN keywords_paths kp ON k.id = kp.keyword_id
                GROUP BY k.id, k.category_id, k.keyword
                ORDER BY file_count DESC, k.id ASC
                LIMIT 100
            """, params=None, fetch="all", use_cache=True)
            
            keywords = []
            if keywords_data:
                # Batch load all word IDs to avoid N+1 queries
                all_word_ids = set()
                keyword_word_map = {}
                
                for row in keywords_data:
                    keyword_id = row[0]
                    keyword_bytes = row[2]
                    try:
                        if keyword_bytes:
                            word_ids = unpack_int_list(keyword_bytes)
                            if word_ids and isinstance(word_ids, list):
                                keyword_word_map[keyword_id] = word_ids
                                all_word_ids.update(word_ids)
                    except Exception as e:
                        logger.warning(f"Error unpickling keyword {keyword_id}: {e}")
                
                # Batch load all words at once
                word_dict = {}
                if all_word_ids:
                    placeholders = ','.join(['%s'] * len(all_word_ids))
                    words_query = f"SELECT id, word FROM words WHERE id IN ({placeholders})"
                    words_result = execute_query(words_query, list(all_word_ids))
                    if words_result:
                        word_dict = {row[0]: row[1] for row in words_result}
                
                # Build keyword list with text
                for row in keywords_data:
                    keyword_id = row[0]
                    file_count = row[3] or 0
                    # Only include keywords that have files
                    if file_count > 0 and keyword_id in keyword_word_map:
                        word_ids = keyword_word_map[keyword_id]
                        words = [word_dict.get(wid, '') for wid in word_ids if wid in word_dict]
                        if words:
                            keyword_text = ' '.join(words)
                            keywords.append({
                                'id': keyword_id,
                                'name': keyword_text,
                                'category_id': row[1],
                                'file_count': file_count
                            })
            
            logger.info(f"✅ Loaded {len(keywords)} keywords from database (query returned {len(keywords_data or [])} rows)")
            

            titles_data = execute_query("""
                SELECT tc.id, tc.title_status, tc.path_id, tc.title_data,
                       CASE WHEN p.id IS NOT NULL THEN 1 ELSE 0 END as file_count
                FROM titles_content tc
                LEFT JOIN paths p ON tc.path_id = p.id
                WHERE tc.title_status = 'Main'
                ORDER BY tc.id DESC
                LIMIT 100
            """)
            
            titles = []
            if titles_data:
                # Batch load all word IDs
                all_title_word_ids = set()
                title_word_map = {}
                
                for row in titles_data:
                    title_id = row[0]
                    title_bytes = row[3]
                    try:
                        if title_bytes:
                            # Validate bytes before unpickling
                            if not isinstance(title_bytes, (bytes, bytearray, memoryview)):
                                continue
                            
                            # Convert to bytes if needed
                            if isinstance(title_bytes, memoryview):
                                title_bytes = bytes(title_bytes)
                            elif not isinstance(title_bytes, bytes):
                                title_bytes = bytes(title_bytes)
                            
                            # Validate minimum size
                            if len(title_bytes) < 2:
                                continue
                            
                            word_ids = unpack_int_list(title_bytes)
                            if word_ids and isinstance(word_ids, list):
                                title_word_map[title_id] = word_ids
                                all_title_word_ids.update(word_ids)
                    except (ValueError, TypeError, EOFError):
                        # Silently skip corrupted data
                        pass
                    except Exception as e:
                        logger.debug(f"Unexpected error unpickling title {title_id}: {type(e).__name__}")
                
                # Batch load all words
                title_word_dict = {}
                if all_title_word_ids:
                    placeholders = ','.join(['%s'] * len(all_title_word_ids))
                    words_query = f"SELECT id, word FROM words WHERE id IN ({placeholders})"
                    words_result = execute_query(words_query, list(all_title_word_ids))
                    if words_result:
                        title_word_dict = {row[0]: row[1] for row in words_result}
                
                # Build title list
                for row in titles_data:
                    title_id = row[0]
                    if title_id in title_word_map:
                        word_ids = title_word_map[title_id]
                        words = [title_word_dict.get(wid, '') for wid in word_ids if wid in title_word_dict]
                        if words:
                            title_text = ' '.join(words)
                            titles.append({
                                'id': title_id,
                                'name': title_text[:100],  # Limit display length
                                'status': row[1],
                                'file_count': row[4] or 0
                            })
            
            # Sources
            sources_data = execute_query("""
                SELECT s.id, s.name, s.job, s.country, s.city,
                       COUNT(DISTINCT p.id) as file_count
                FROM sources s
                LEFT JOIN hashs h ON s.id = h.source_id
                LEFT JOIN paths p ON h.id = p.hash_id
                GROUP BY s.id, s.name, s.job, s.country, s.city
                ORDER BY file_count DESC, s.name ASC
                LIMIT 100
            """)
            
            sources = []
            for row in (sources_data or []):
                sources.append({
                    'id': row[0],
                    'name': row[1] or 'Unnamed Source',
                    'job': row[2] or 'N/A',
                    'country': row[3] or 'N/A',
                    'city': row[4] or 'N/A',
                    'file_count': row[5] or 0
                })
            
            # Sides
            sides_data = execute_query("""
                SELECT si.id, si.name, si.importance,
                       COUNT(DISTINCT p.id) as file_count
                FROM sides si
                LEFT JOIN hashs h ON si.id = h.side_id
                LEFT JOIN paths p ON h.id = p.hash_id
                GROUP BY si.id, si.name, si.importance
                ORDER BY si.importance DESC, si.name ASC
                LIMIT 100
            """)
            
            sides = []
            for row in (sides_data or []):
                sides.append({
                    'id': row[0],
                    'name': row[1] or 'Unnamed Side',
                    'importance': float(row[2]) if row[2] else 0.0,
                    'file_count': row[3] or 0
                })
            

            hashs_data = execute_query("""
                SELECT h.id, h.hash, h.side_id, h.source_id,
                       COUNT(DISTINCT p.id) as file_count,
                       COUNT(DISTINCT h2.id) as hash_variants
                FROM hashs h
                LEFT JOIN paths p ON h.id = p.hash_id
                LEFT JOIN hashs h2 ON h.hash = h2.hash AND (h.source_id != h2.source_id OR h.side_id != h2.side_id)
                GROUP BY h.id, h.hash, h.side_id, h.source_id
                HAVING COUNT(DISTINCT p.id) > 1 OR COUNT(DISTINCT h2.id) > 0
                ORDER BY file_count DESC, hash_variants DESC
                LIMIT 100
            """)
            
            hashs = []
            for row in (hashs_data or []):
                hashs.append({
                    'id': row[0],
                    'name': row[1] or 'Unknown Hash',
                    'side_id': row[2],
                    'source_id': row[3],
                    'file_count': row[4] or 0
                })
            
            stats = get_archive_statistics()
            
            # Top categories by file count
            top_categories = categories[:10] if len(categories) > 10 else categories
            
            # Top sources by file count
            top_sources = sources[:10] if len(sources) > 10 else sources
            
            # Category distribution data
            category_distribution = []
            for cat in categories[:15]:
                category_distribution.append({
                    'name': cat['name'],
                    'file_count': cat['file_count']
                })
            
            response = make_response(render_template('file/File_Management_Analysis_System.html',
                                 categories=categories,
                                 keywords=keywords,
                                 titles=titles,
                                 sources=sources,
                                 sides=sides,
                                 hashs=hashs,
                                 stats=stats,
                                 top_categories=top_categories,
                                 top_sources=top_sources,
                                 category_distribution=category_distribution))
            response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
            response.headers['Pragma'] = 'no-cache'
            response.headers['Expires'] = '0'
            return response
            
        except Exception as e:
            logger.error(f"Error loading archives page: {e}")
            import traceback
            logger.error(traceback.format_exc())
            flash("Error loading archives page", "error")
            return render_template('file/File_Management_Analysis_System.html',
                                 categories=[],
                                 keywords=[],
                                 titles=[],
                                 sources=[],
                                 sides=[],
                                 hashs=[],
                                 stats={},
                                 top_categories=[],
                                 top_sources=[],
                                 category_distribution=[])
    
    @app.route('/api/archives/search')
    def api_archives_search():
        """API endpoint for searching archives"""
        try:
            section = request.args.get('section', '')
            search_query = request.args.get('q', '').strip()
            
            if not section:
                return jsonify({'success': False, 'error': 'Section parameter required'}), 400
            
            results = []
            
            if section == 'category':
                if search_query:
                    query = """
                        SELECT c.id, w.word as name, 
                               COUNT(DISTINCT p.id) as file_count
                        FROM categorys c
                        JOIN words w ON c.word_id = w.id
                        LEFT JOIN words_categorys wc ON c.id = wc.category_id
                        LEFT JOIN words_paths wp ON wc.word_id = wp.word_id
                        LEFT JOIN paths p ON wp.path_id = p.id
                        WHERE w.word ILIKE %s
                        GROUP BY c.id, w.word
                        ORDER BY file_count DESC, w.word ASC
                        LIMIT 100
                    """
                    data = execute_query(query, (f'%{search_query}%',))
                else:
                    query = """
                        SELECT c.id, w.word as name, 
                               COUNT(DISTINCT p.id) as file_count
                        FROM categorys c
                        JOIN words w ON c.word_id = w.id
                        LEFT JOIN words_categorys wc ON c.id = wc.category_id
                        LEFT JOIN words_paths wp ON wc.word_id = wp.word_id
                        LEFT JOIN paths p ON wp.path_id = p.id
                        GROUP BY c.id, w.word
                        ORDER BY file_count DESC, w.word ASC
                        LIMIT 100
                    """
                    data = execute_query(query)
                
                for row in (data or []):
                    results.append({
                        'id': row[0],
                        'name': row[1] or 'Unnamed Category',
                        'category': 'Category',
                        'details': f'{row[2] or 0} files',
                        'file_count': row[2] or 0
                    })
            
            elif section == 'keywords':
                # 🚀 PERFORMANCE: Load top 500 keywords max to avoid N+1 query problem
                # Even with search, we limit results for reasonable performance
                query = """
                    SELECT k.id, k.category_id,
                           COUNT(DISTINCT kp.path_id) as file_count
                    FROM keywords k
                    LEFT JOIN keywords_paths kp ON k.id = kp.keyword_id
                    GROUP BY k.id, k.category_id
                    ORDER BY file_count DESC, k.id ASC
                    LIMIT 500
                """
                data = execute_query(query, params=None, fetch="all", use_cache=True)
                
                for row in (data or []):
                    keyword_text = load_text_keyword(row[0])
                    if keyword_text:
                        # Filter by search query if provided
                        if search_query and search_query.lower() not in keyword_text.lower():
                            continue
                        results.append({
                            'id': row[0],
                            'name': keyword_text,  # Full text, no truncation
                            'category': 'Keywords',
                            'details': f'{row[2] or 0} files',
                            'file_count': row[2] or 0
                        })
            
            elif section == 'titles':
                query = """
                    SELECT tc.id, tc.title_status, tc.path_id,
                           CASE WHEN p.id IS NOT NULL THEN 1 ELSE 0 END as file_count
                    FROM titles_content tc
                    LEFT JOIN paths p ON tc.path_id = p.id
                    WHERE tc.title_status = 'Main'
                    ORDER BY tc.id DESC
                    LIMIT 100
                """
                data = execute_query(query)
                
                for row in (data or []):
                    title_text = load_text_title(row[0])
                    if title_text and (not search_query or search_query.lower() in title_text.lower()):
                        results.append({
                            'id': row[0],
                            'name': title_text[:100],
                            'category': 'Titles',
                            'details': f'Status: {row[1]} ({row[3] or 0} files)',
                            'file_count': row[3] or 0
                        })
            
            elif section == 'sources':
                if search_query:
                    query = """
                        SELECT s.id, s.name, s.job, s.country, s.city,
                               COUNT(DISTINCT p.id) as file_count
                        FROM sources s
                        LEFT JOIN hashs h ON s.id = h.source_id
                        LEFT JOIN paths p ON h.id = p.hash_id
                        WHERE s.name ILIKE %s OR s.job ILIKE %s OR s.country ILIKE %s
                        GROUP BY s.id, s.name, s.job, s.country, s.city
                        ORDER BY file_count DESC, s.name ASC
                        LIMIT 100
                    """
                    pattern = f'%{search_query}%'
                    data = execute_query(query, (pattern, pattern, pattern))
                else:
                    query = """
                        SELECT s.id, s.name, s.job, s.country, s.city,
                               COUNT(DISTINCT p.id) as file_count
                        FROM sources s
                        LEFT JOIN hashs h ON s.id = h.source_id
                        LEFT JOIN paths p ON h.id = p.hash_id
                        GROUP BY s.id, s.name, s.job, s.country, s.city
                        ORDER BY file_count DESC, s.name ASC
                        LIMIT 100
                    """
                    data = execute_query(query)
                
                for row in (data or []):
                    results.append({
                        'id': row[0],
                        'name': row[1] or 'Unnamed Source',
                        'category': 'Sources',
                        'details': f'{row[2] or "N/A"} - {row[3] or "N/A"} ({row[5] or 0} files)',
                        'file_count': row[5] or 0
                    })
            
            elif section == 'sides':
                if search_query:
                    query = """
                        SELECT si.id, si.name, si.importance,
                               COUNT(DISTINCT p.id) as file_count
                        FROM sides si
                        LEFT JOIN hashs h ON si.id = h.side_id
                        LEFT JOIN paths p ON h.id = p.hash_id
                        WHERE si.name ILIKE %s
                        GROUP BY si.id, si.name, si.importance
                        ORDER BY si.importance DESC, si.name ASC
                        LIMIT 100
                    """
                    data = execute_query(query, (f'%{search_query}%',))
                else:
                    query = """
                        SELECT si.id, si.name, si.importance,
                               COUNT(DISTINCT p.id) as file_count
                        FROM sides si
                        LEFT JOIN hashs h ON si.id = h.side_id
                        LEFT JOIN paths p ON h.id = p.hash_id
                        GROUP BY si.id, si.name, si.importance
                        ORDER BY si.importance DESC, si.name ASC
                        LIMIT 100
                    """
                    data = execute_query(query)
                
                for row in (data or []):
                    results.append({
                        'id': row[0],
                        'name': row[1] or 'Unnamed Side',
                        'category': 'Sides',
                        'details': f'Importance: {row[2] or 0.0} ({row[3] or 0} files)',
                        'file_count': row[3] or 0
                    })
            
            elif section == 'hash':
                if search_query:
                    query = """
                        SELECT h.id, h.hash, h.side_id, h.source_id,
                               COUNT(DISTINCT p.id) as file_count,
                               COUNT(DISTINCT h2.id) as hash_variants
                        FROM hashs h
                        LEFT JOIN paths p ON h.id = p.hash_id
                        LEFT JOIN hashs h2 ON h.hash = h2.hash AND (h.source_id != h2.source_id OR h.side_id != h2.side_id)
                        WHERE h.hash ILIKE %s
                        GROUP BY h.id, h.hash, h.side_id, h.source_id
                        HAVING COUNT(DISTINCT p.id) > 1 OR COUNT(DISTINCT h2.id) > 0
                        ORDER BY file_count DESC, hash_variants DESC
                        LIMIT 100
                    """
                    data = execute_query(query, (f'%{search_query}%',))
                else:
                    query = """
                        SELECT h.id, h.hash, h.side_id, h.source_id,
                               COUNT(DISTINCT p.id) as file_count,
                               COUNT(DISTINCT h2.id) as hash_variants
                        FROM hashs h
                        LEFT JOIN paths p ON h.id = p.hash_id
                        LEFT JOIN hashs h2 ON h.hash = h2.hash AND (h.source_id != h2.source_id OR h.side_id != h2.side_id)
                        GROUP BY h.id, h.hash, h.side_id, h.source_id
                        HAVING COUNT(DISTINCT p.id) > 1 OR COUNT(DISTINCT h2.id) > 0
                        ORDER BY file_count DESC, hash_variants DESC
                        LIMIT 100
                    """
                    data = execute_query(query)
                
                for row in (data or []):
                    results.append({
                        'id': row[0],
                        'name': row[1] or 'Unknown Hash',
                        'category': 'Hash',
                        'details': f'{row[4] or 0} files',
                        'file_count': row[4] or 0
                    })
            
            return jsonify({'success': True, 'results': results})
            
        except Exception as e:
            logger.error(f"Error searching archives: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return client_error(e, subsystem='Api.routes.archives', success_key='success', status=500)
    
    @app.route('/api/archives/files')
    def api_archives_files():
        """API endpoint for getting files associated with an archive item"""
        try:
            section = request.args.get('section', '').strip()
            item_id = request.args.get('id', type=int)
            limit = request.args.get('limit', 50, type=int)
            offset = request.args.get('offset', 0, type=int)
            page = request.args.get('page', 1, type=int)
            source_id = request.args.get('source_id', type=int)
            side_id = request.args.get('side_id', type=int)
            
            # Enforce reasonable limits for performance (max 1000 per page)
            limit = min(max(1, limit), 1000)
            
            logger.info(f"API request: section={section}, item_id={item_id}, page={page}, limit={limit}, offset={offset}, source_id={source_id}, side_id={side_id}")
            
            if not section or not item_id:
                logger.warning(f"Missing parameters: section={section}, item_id={item_id}")
                return jsonify({'success': False, 'error': 'Section and ID required'}), 400
            
            # Calculate offset from page if provided
            if page > 1:
                offset = (page - 1) * limit
            elif offset < 0:
                offset = 0
            
            files = []
            total_count = 0
            total_size = 0
            
            if section == 'category':
                # Build WHERE clause with optional source/side filters
                where_clause = "wc.category_id = %s"
                query_params = [item_id]
                
                if source_id:
                    where_clause += " AND h.source_id = %s"
                    query_params.append(source_id)
                
                if side_id:
                    where_clause += " AND h.side_id = %s"
                    query_params.append(side_id)
                
                # Get total count - must match the files query structure exactly
                # Using DISTINCT to ensure accurate count when files have multiple word associations
                count_query = f"""
                    SELECT COUNT(DISTINCT p.id)
                    FROM paths p
                    JOIN words_paths wp ON wp.path_id = p.id
                    JOIN words_categorys wc ON wc.word_id = wp.word_id
                    LEFT JOIN hashs h ON p.hash_id = h.id
                    WHERE {where_clause}
                """
                count_result = execute_query(count_query, tuple(query_params), fetch="one")
                
                if count_result:
                    total_count = count_result[0] if isinstance(count_result, (tuple, list)) else (count_result if count_result else 0)
                else:
                    total_count = 0
                
                # Get total size separately using a subquery to sum distinct file sizes
                if total_count > 0:
                    size_query = f"""
                        SELECT COALESCE(SUM(file_size), 0)
                        FROM (
                            SELECT DISTINCT p.id, p.file_size
                            FROM paths p
                            JOIN words_paths wp ON wp.path_id = p.id
                            JOIN words_categorys wc ON wc.word_id = wp.word_id
                            LEFT JOIN hashs h ON p.hash_id = h.id
                            WHERE {where_clause}
                        ) AS distinct_files
                    """
                    size_result = execute_query(size_query, tuple(query_params), fetch="one")
                    total_size = size_result[0] if size_result and isinstance(size_result, (tuple, list)) else (size_result if size_result else 0)
                else:
                    total_size = 0
                
                # Files query - using DISTINCT to ensure each file appears only once
                # ORDER BY ensures consistent pagination across pages
                files_query = f"""
                    SELECT DISTINCT
                        p.id, p.file_name, p.file_path, p.file_size, p.file_type,
                        p.file_status, p.file_date, p.date_creation,
                        COALESCE(s.name, 'Unknown') as source_name,
                        COALESCE(si.name, 'Unknown') as side_name
                    FROM paths p
                    JOIN words_paths wp ON wp.path_id = p.id
                    JOIN words_categorys wc ON wc.word_id = wp.word_id
                    LEFT JOIN hashs h ON p.hash_id = h.id
                    LEFT JOIN sources s ON h.source_id = s.id
                    LEFT JOIN sides si ON h.side_id = si.id
                    WHERE {where_clause}
                    ORDER BY p.file_date DESC NULLS LAST, p.id DESC
                    LIMIT %s OFFSET %s
                """
                files_params = query_params + [limit, offset]
                files_data = execute_query(files_query, tuple(files_params), fetch="all")
                
                for row in (files_data or []):
                    files.append({
                        'id': row[0],
                        'name': row[1] or 'Unnamed File',
                        'path': row[2] or '',
                        'size': row[3] or 0,
                        'type': row[4] or 'Unknown',
                        'status': row[5] or 'Unknown',
                        'file_date': row[6].isoformat() if row[6] else None,
                        'date_creation': row[7].isoformat() if row[7] else None,
                        'source': row[8] or 'Unknown',
                        'side': row[9] or 'Unknown'
                    })
            
            elif section == 'keywords':
                # Build WHERE clause with optional source/side filters
                where_clause = "kp.keyword_id = %s"
                query_params = [item_id]
                
                if source_id:
                    where_clause += " AND h.source_id = %s"
                    query_params.append(source_id)
                
                if side_id:
                    where_clause += " AND h.side_id = %s"
                    query_params.append(side_id)
                
                # Get total count - must match the files query structure exactly
                count_query = f"""
                    SELECT COUNT(DISTINCT p.id)
                    FROM paths p
                    JOIN keywords_paths kp ON kp.path_id = p.id
                    LEFT JOIN hashs h ON p.hash_id = h.id
                    WHERE {where_clause}
                """
                count_result = execute_query(count_query, tuple(query_params), fetch="one")
                
                if count_result:
                    total_count = count_result[0] if isinstance(count_result, (tuple, list)) else (count_result if count_result else 0)
                else:
                    total_count = 0
                
                # Get total size separately using a subquery to sum distinct file sizes
                if total_count > 0:
                    size_query = f"""
                        SELECT COALESCE(SUM(file_size), 0)
                        FROM (
                            SELECT DISTINCT p.id, p.file_size
                            FROM paths p
                            JOIN keywords_paths kp ON kp.path_id = p.id
                            LEFT JOIN hashs h ON p.hash_id = h.id
                            WHERE {where_clause}
                        ) AS distinct_files
                    """
                    size_result = execute_query(size_query, tuple(query_params), fetch="one")
                    total_size = size_result[0] if size_result and isinstance(size_result, (tuple, list)) else (size_result if size_result else 0)
                else:
                    total_size = 0
                
                # Files query - using DISTINCT to ensure each file appears only once
                # ORDER BY ensures consistent pagination across pages
                files_query = f"""
                    SELECT DISTINCT
                        p.id, p.file_name, p.file_path, p.file_size, p.file_type,
                        p.file_status, p.file_date, p.date_creation,
                        COALESCE(s.name, 'Unknown') as source_name,
                        COALESCE(si.name, 'Unknown') as side_name
                    FROM paths p
                    JOIN keywords_paths kp ON kp.path_id = p.id
                    LEFT JOIN hashs h ON p.hash_id = h.id
                    LEFT JOIN sources s ON h.source_id = s.id
                    LEFT JOIN sides si ON h.side_id = si.id
                    WHERE {where_clause}
                    ORDER BY p.file_date DESC NULLS LAST, p.id DESC
                    LIMIT %s OFFSET %s
                """
                files_params = query_params + [limit, offset]
                files_data = execute_query(files_query, tuple(files_params), fetch="all")
                
                for row in (files_data or []):
                    files.append({
                        'id': row[0],
                        'name': row[1] or 'Unnamed File',
                        'path': row[2] or '',
                        'size': row[3] or 0,
                        'type': row[4] or 'Unknown',
                        'status': row[5] or 'Unknown',
                        'file_date': row[6].isoformat() if row[6] else None,
                        'date_creation': row[7].isoformat() if row[7] else None,
                        'source': row[8] or 'Unknown',
                        'side': row[9] or 'Unknown'
                    })
            
            elif section == 'titles':
                # Titles are linked directly to paths via path_id
                count_result = execute_query("""
                    SELECT COUNT(*), COALESCE(SUM(p.file_size), 0)
                    FROM titles_content tc
                    JOIN paths p ON tc.path_id = p.id
                    WHERE tc.id = %s
                """, (item_id,), fetch="one")
                
                if count_result:
                    if isinstance(count_result, tuple) and len(count_result) >= 2:
                        total_count = count_result[0] or 0
                        total_size = count_result[1] or 0
                    else:
                        total_count = count_result or 0
                
                files_data = execute_query("""
                    SELECT DISTINCT
                        p.id, p.file_name, p.file_path, p.file_size, p.file_type,
                        p.file_status, p.file_date, p.date_creation,
                        COALESCE(s.name, 'Unknown') as source_name,
                        COALESCE(si.name, 'Unknown') as side_name
                    FROM titles_content tc
                    JOIN paths p ON tc.path_id = p.id
                    LEFT JOIN hashs h ON p.hash_id = h.id
                    LEFT JOIN sources s ON h.source_id = s.id
                    LEFT JOIN sides si ON h.side_id = si.id
                    WHERE tc.id = %s
                    ORDER BY p.file_date DESC
                    LIMIT %s OFFSET %s
                """, (item_id, limit, offset), fetch="all")
                
                for row in (files_data or []):
                    files.append({
                        'id': row[0],
                        'name': row[1] or 'Unnamed File',
                        'path': row[2] or '',
                        'size': row[3] or 0,
                        'type': row[4] or 'Unknown',
                        'status': row[5] or 'Unknown',
                        'file_date': row[6].isoformat() if row[6] else None,
                        'date_creation': row[7].isoformat() if row[7] else None,
                        'source': row[8] or 'Unknown',
                        'side': row[9] or 'Unknown'
                    })
            
            elif section == 'sources':
                # Sources are linked through hashs
                logger.info(f"Fetching files for source_id={item_id}")
                count_result = execute_query("""
                    SELECT COUNT(DISTINCT p.id), COALESCE(SUM(p.file_size), 0)
                    FROM paths p
                    JOIN hashs h ON p.hash_id = h.id
                    WHERE h.source_id = %s
                """, (item_id,), fetch="one")
                
                logger.info(f"Count result for source_id={item_id}: {count_result}")
                
                if count_result:
                    if isinstance(count_result, tuple) and len(count_result) >= 2:
                        total_count = count_result[0] or 0
                        total_size = count_result[1] or 0
                    else:
                        total_count = count_result or 0
                else:
                    total_count = 0
                    total_size = 0
                
                logger.info(f"Total count for source_id={item_id}: {total_count}")
                
                files_data = execute_query("""
                    SELECT DISTINCT
                        p.id, p.file_name, p.file_path, p.file_size, p.file_type,
                        p.file_status, p.file_date, p.date_creation,
                        COALESCE(s.name, 'Unknown') as source_name,
                        COALESCE(si.name, 'Unknown') as side_name
                    FROM paths p
                    JOIN hashs h ON p.hash_id = h.id
                    LEFT JOIN sources s ON h.source_id = s.id
                    LEFT JOIN sides si ON h.side_id = si.id
                    WHERE h.source_id = %s
                    ORDER BY p.file_date DESC
                    LIMIT %s OFFSET %s
                """, (item_id, limit, offset), fetch="all")
                
                logger.info(f"Files data query returned {len(files_data) if files_data else 0} rows for source_id={item_id}")
                
                for row in (files_data or []):
                    files.append({
                        'id': row[0],
                        'name': row[1] or 'Unnamed File',
                        'path': row[2] or '',
                        'size': row[3] or 0,
                        'type': row[4] or 'Unknown',
                        'status': row[5] or 'Unknown',
                        'file_date': row[6].isoformat() if row[6] else None,
                        'date_creation': row[7].isoformat() if row[7] else None,
                        'source': row[8] or 'Unknown',
                        'side': row[9] or 'Unknown'
                    })
            
            elif section == 'sides':
                # Sides are linked through hashs
                count_result = execute_query("""
                    SELECT COUNT(DISTINCT p.id), COALESCE(SUM(p.file_size), 0)
                    FROM paths p
                    JOIN hashs h ON p.hash_id = h.id
                    WHERE h.side_id = %s
                """, (item_id,), fetch="one")
                
                if count_result:
                    if isinstance(count_result, tuple) and len(count_result) >= 2:
                        total_count = count_result[0] or 0
                        total_size = count_result[1] or 0
                    else:
                        total_count = count_result or 0
                
                files_data = execute_query("""
                    SELECT DISTINCT
                        p.id, p.file_name, p.file_path, p.file_size, p.file_type,
                        p.file_status, p.file_date, p.date_creation,
                        COALESCE(s.name, 'Unknown') as source_name,
                        COALESCE(si.name, 'Unknown') as side_name
                    FROM paths p
                    JOIN hashs h ON p.hash_id = h.id
                    LEFT JOIN sources s ON h.source_id = s.id
                    LEFT JOIN sides si ON h.side_id = si.id
                    WHERE h.side_id = %s
                    ORDER BY p.file_date DESC
                    LIMIT %s OFFSET %s
                """, (item_id, limit, offset), fetch="all")
                
                for row in (files_data or []):
                    files.append({
                        'id': row[0],
                        'name': row[1] or 'Unnamed File',
                        'path': row[2] or '',
                        'size': row[3] or 0,
                        'type': row[4] or 'Unknown',
                        'status': row[5] or 'Unknown',
                        'file_date': row[6].isoformat() if row[6] else None,
                        'date_creation': row[7].isoformat() if row[7] else None,
                        'source': row[8] or 'Unknown',
                        'side': row[9] or 'Unknown'
                    })
            
            elif section == 'hash':
                # For hash section, show all files with the same hash value
                # Get the hash value first
                hash_info = execute_query("""
                    SELECT hash FROM hashs WHERE id = %s
                """, (item_id,), fetch="one")
                
                if hash_info:
                    # execute_query with fetch="one" returns the value directly for single column
                    hash_value = hash_info if isinstance(hash_info, str) else (hash_info[0] if isinstance(hash_info, (tuple, list)) and len(hash_info) > 0 else None)
                    
                    if hash_value:
                        # Count all files with this hash (across all sources/sides)
                        count_result = execute_query("""
                            SELECT COUNT(DISTINCT p.id), COALESCE(SUM(p.file_size), 0)
                            FROM paths p
                            JOIN hashs h ON p.hash_id = h.id
                            WHERE h.hash = %s
                        """, (hash_value,), fetch="one")
                        
                        if count_result:
                            if isinstance(count_result, tuple) and len(count_result) >= 2:
                                total_count = count_result[0] or 0
                                total_size = count_result[1] or 0
                            else:
                                total_count = count_result or 0
                        
                        # Get all files with this hash (showing all sources/sides)
                        files_data = execute_query("""
                            SELECT DISTINCT
                                p.id, p.file_name, p.file_path, p.file_size, p.file_type,
                                p.file_status, p.file_date, p.date_creation,
                                COALESCE(s.name, 'Unknown') as source_name,
                                COALESCE(si.name, 'Unknown') as side_name
                            FROM paths p
                            JOIN hashs h ON p.hash_id = h.id
                            LEFT JOIN sources s ON h.source_id = s.id
                            LEFT JOIN sides si ON h.side_id = si.id
                            WHERE h.hash = %s
                            ORDER BY p.file_date DESC
                            LIMIT %s OFFSET %s
                        """, (hash_value, limit, offset), fetch="all")
                        
                        for row in (files_data or []):
                            files.append({
                                'id': row[0],
                                'name': row[1] or 'Unnamed File',
                                'path': row[2] or '',
                                'size': row[3] or 0,
                                'type': row[4] or 'Unknown',
                                'status': row[5] or 'Unknown',
                                'file_date': row[6].isoformat() if row[6] else None,
                                'date_creation': row[7].isoformat() if row[7] else None,
                                'source': row[8] or 'Unknown',
                                'side': row[9] or 'Unknown'
                            })
            
            elif section == 'address':

                logger.info(f"Fetching files for address (word_id={item_id})")
                
                # Count files containing this word
                count_result = execute_query("""
                    SELECT COUNT(DISTINCT p.id), COALESCE(SUM(p.file_size), 0)
                    FROM paths p
                    JOIN words_paths wp ON wp.path_id = p.id
                    WHERE wp.word_id = %s
                """, (item_id,), fetch="one")
                
                if count_result:
                    if isinstance(count_result, tuple) and len(count_result) >= 2:
                        total_count = count_result[0] or 0
                        total_size = count_result[1] or 0
                    else:
                        total_count = count_result or 0
                
                logger.info(f"Total count for address (word_id={item_id}): {total_count}")
                
                # Get files containing this word
                files_data = execute_query("""
                    SELECT DISTINCT
                        p.id, p.file_name, p.file_path, p.file_size, p.file_type,
                        p.file_status, p.file_date, p.date_creation,
                        COALESCE(s.name, 'Unknown') as source_name,
                        COALESCE(si.name, 'Unknown') as side_name
                    FROM paths p
                    JOIN words_paths wp ON wp.path_id = p.id
                    LEFT JOIN hashs h ON p.hash_id = h.id
                    LEFT JOIN sources s ON h.source_id = s.id
                    LEFT JOIN sides si ON h.side_id = si.id
                    WHERE wp.word_id = %s
                    ORDER BY p.file_date DESC
                    LIMIT %s OFFSET %s
                """, (item_id, limit, offset), fetch="all")
                
                logger.info(f"Files data query returned {len(files_data) if files_data else 0} rows for address (word_id={item_id})")
                
                for row in (files_data or []):
                    files.append({
                        'id': row[0],
                        'name': row[1] or 'Unnamed File',
                        'path': row[2] or '',
                        'size': row[3] or 0,
                        'type': row[4] or 'Unknown',
                        'status': row[5] or 'Unknown',
                        'file_date': row[6].isoformat() if row[6] else None,
                        'date_creation': row[7].isoformat() if row[7] else None,
                        'source': row[8] or 'Unknown',
                        'side': row[9] or 'Unknown'
                    })
            else:
                # Unknown section
                logger.warning(f"Unknown section requested: {section}")
                return jsonify({
                    'success': False,
                    'error': f'Unknown section: {section}'
                }), 400
            
            # Calculate pagination info
            total_pages = (total_count + limit - 1) // limit if total_count > 0 else 1
            current_page = page if page > 0 else (offset // limit) + 1
            
            logger.info(f"Returning {len(files)} files for section={section}, item_id={item_id}, total={total_count}")
            
            return jsonify({
                'success': True,
                'files': files,
                'pagination': {
                    'total': total_count,
                    'total_size': total_size,
                    'page': current_page,
                    'per_page': limit,
                    'total_pages': total_pages,
                    'has_prev': current_page > 1,
                    'has_next': current_page < total_pages
                }
            })
            
        except Exception as e:
            logger.error(f"Error fetching archive files: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return client_error(e, subsystem='Api.routes.archives', success_key='success', status=500)
    
    @app.route('/api/archives/source-categories-keywords')
    def api_source_categories_keywords():
        """API endpoint for getting categories and keywords for a specific source with file counts"""
        try:
            source_id = request.args.get('source_id', type=int)
            page = request.args.get('page', 1, type=int)
            limit = request.args.get('limit', 20, type=int)
            offset = (page - 1) * limit
            
            if not source_id:
                return jsonify({'success': False, 'error': 'source_id required'}), 400
            
            # Get categories for this source
            categories_query = """
                SELECT DISTINCT c.id, w.word as category_name,
                       COUNT(DISTINCT p.id) as file_count
                FROM categorys c
                JOIN words w ON c.word_id = w.id
                JOIN words_categorys wc ON c.id = wc.category_id
                JOIN words_paths wp ON wc.word_id = wp.word_id
                JOIN paths p ON wp.path_id = p.id
                JOIN hashs h ON p.hash_id = h.id
                WHERE h.source_id = %s
                GROUP BY c.id, w.word
                ORDER BY file_count DESC, w.word ASC
                LIMIT %s OFFSET %s
            """
            try:
                categories_data = execute_query(categories_query, (source_id, limit, offset), fetch="all")
            except Exception as query_error:
                logger.error(f"Error executing categories query: {query_error}")
                categories_data = []
            
            # Get total count of categories
            total_categories_query = """
                SELECT COUNT(DISTINCT c.id)
                FROM categorys c
                JOIN words_categorys wc ON c.id = wc.category_id
                JOIN words_paths wp ON wc.word_id = wp.word_id
                JOIN paths p ON wp.path_id = p.id
                JOIN hashs h ON p.hash_id = h.id
                WHERE h.source_id = %s
            """
            try:
                total_categories_result = execute_query(total_categories_query, (source_id,), fetch="one")
                total_categories = total_categories_result[0] if total_categories_result else 0
            except Exception as query_error:
                logger.error(f"Error executing total categories query: {query_error}")
                total_categories = len(categories_data) if categories_data else 0
            
            categories = []
            for row in (categories_data or []):
                categories.append({
                    'id': row[0],
                    'name': row[1] or 'Unnamed Category',
                    'file_count': row[2] or 0
                })
            
            # Get keywords for this source
            keywords_query = """
                SELECT DISTINCT k.id, k.category_id, k.keyword,
                       COUNT(DISTINCT kp.path_id) as file_count
                FROM keywords k
                JOIN keywords_paths kp ON k.id = kp.keyword_id
                JOIN paths p ON kp.path_id = p.id
                JOIN hashs h ON p.hash_id = h.id
                WHERE h.source_id = %s
                GROUP BY k.id, k.category_id, k.keyword
                ORDER BY file_count DESC, k.id ASC
                LIMIT %s OFFSET %s
            """
            try:
                keywords_data = execute_query(keywords_query, (source_id, limit, offset), fetch="all")
            except Exception as query_error:
                logger.error(f"Error executing keywords query: {query_error}")
                keywords_data = []
            
            # Get total count of keywords
            total_keywords_query = """
                SELECT COUNT(DISTINCT k.id)
                FROM keywords k
                JOIN keywords_paths kp ON k.id = kp.keyword_id
                JOIN paths p ON kp.path_id = p.id
                JOIN hashs h ON p.hash_id = h.id
                WHERE h.source_id = %s
            """
            try:
                total_keywords_result = execute_query(total_keywords_query, (source_id,), fetch="one")
                total_keywords = total_keywords_result[0] if total_keywords_result else 0
            except Exception as query_error:
                logger.error(f"Error executing total keywords query: {query_error}")
                total_keywords = len(keywords_data) if keywords_data else 0
            
            keywords = []
            if keywords_data:
                for row in keywords_data:
                    keyword_id = row[0]
                    keyword_bytes = row[2]
                    try:
                        if keyword_bytes:
                            word_ids = unpack_int_list(keyword_bytes)
                            if word_ids and isinstance(word_ids, list):
                                # Batch load words
                                if word_ids:
                                    placeholders = ','.join(['%s'] * len(word_ids))
                                    words_query = f"SELECT id, word FROM words WHERE id IN ({placeholders})"
                                    words_result = execute_query(words_query, list(word_ids))
                                    if words_result:
                                        word_dict = {row[0]: row[1] for row in words_result}
                                        words = [word_dict.get(wid, '') for wid in word_ids if wid in word_dict]
                                        if words:
                                            keyword_text = ' '.join(words)
                                            keywords.append({
                                                'id': keyword_id,
                                                'name': keyword_text,
                                                'category_id': row[1],
                                                'file_count': row[3] or 0
                                            })
                    except Exception as e:
                        logger.warning(f"Error unpickling keyword {keyword_id}: {e}")
            
            # Calculate pagination
            total_categories_pages = (total_categories + limit - 1) // limit if total_categories > 0 else 1
            total_keywords_pages = (total_keywords + limit - 1) // limit if total_keywords > 0 else 1
            
            return jsonify({
                'success': True,
                'categories': categories,
                'keywords': keywords,
                'pagination': {
                    'categories': {
                        'total': total_categories,
                        'page': page,
                        'per_page': limit,
                        'total_pages': total_categories_pages,
                        'has_prev': page > 1,
                        'has_next': page < total_categories_pages
                    },
                    'keywords': {
                        'total': total_keywords,
                        'page': page,
                        'per_page': limit,
                        'total_pages': total_keywords_pages,
                        'has_prev': page > 1,
                        'has_next': page < total_keywords_pages
                    }
                }
            })
            
        except Exception as e:
            logger.error(f"Error fetching source categories/keywords: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return client_error(e, subsystem='Api.routes.archives', success_key='success', status=500)
    
    @app.route('/api/archives/side-categories-keywords')
    def api_side_categories_keywords():
        """API endpoint for getting categories and keywords for a specific side with file counts"""
        try:
            side_id = request.args.get('side_id', type=int)
            page = request.args.get('page', 1, type=int)
            limit = request.args.get('limit', 20, type=int)
            offset = (page - 1) * limit
            
            if not side_id:
                return jsonify({'success': False, 'error': 'side_id required'}), 400
            
            # Get categories for this side
            categories_query = """
                SELECT DISTINCT c.id, w.word as category_name,
                       COUNT(DISTINCT p.id) as file_count
                FROM categorys c
                JOIN words w ON c.word_id = w.id
                JOIN words_categorys wc ON c.id = wc.category_id
                JOIN words_paths wp ON wc.word_id = wp.word_id
                JOIN paths p ON wp.path_id = p.id
                JOIN hashs h ON p.hash_id = h.id
                WHERE h.side_id = %s
                GROUP BY c.id, w.word
                ORDER BY file_count DESC, w.word ASC
                LIMIT %s OFFSET %s
            """
            try:
                categories_data = execute_query(categories_query, (side_id, limit, offset), fetch="all")
            except Exception as query_error:
                logger.error(f"Error executing categories query: {query_error}")
                categories_data = []
            
            # Get total count of categories
            total_categories_query = """
                SELECT COUNT(DISTINCT c.id)
                FROM categorys c
                JOIN words_categorys wc ON c.id = wc.category_id
                JOIN words_paths wp ON wc.word_id = wp.word_id
                JOIN paths p ON wp.path_id = p.id
                JOIN hashs h ON p.hash_id = h.id
                WHERE h.side_id = %s
            """
            try:
                total_categories_result = execute_query(total_categories_query, (side_id,), fetch="one")
                total_categories = total_categories_result[0] if total_categories_result else 0
            except Exception as query_error:
                logger.error(f"Error executing total categories query: {query_error}")
                total_categories = len(categories_data) if categories_data else 0
            
            categories = []
            for row in (categories_data or []):
                categories.append({
                    'id': row[0],
                    'name': row[1] or 'Unnamed Category',
                    'file_count': row[2] or 0
                })
            
            # Get keywords for this side
            keywords_query = """
                SELECT DISTINCT k.id, k.category_id, k.keyword,
                       COUNT(DISTINCT kp.path_id) as file_count
                FROM keywords k
                JOIN keywords_paths kp ON k.id = kp.keyword_id
                JOIN paths p ON kp.path_id = p.id
                JOIN hashs h ON p.hash_id = h.id
                WHERE h.side_id = %s
                GROUP BY k.id, k.category_id, k.keyword
                ORDER BY file_count DESC, k.id ASC
                LIMIT %s OFFSET %s
            """
            try:
                keywords_data = execute_query(keywords_query, (side_id, limit, offset), fetch="all")
            except Exception as query_error:
                logger.error(f"Error executing keywords query: {query_error}")
                keywords_data = []
            
            # Get total count of keywords
            total_keywords_query = """
                SELECT COUNT(DISTINCT k.id)
                FROM keywords k
                JOIN keywords_paths kp ON k.id = kp.keyword_id
                JOIN paths p ON kp.path_id = p.id
                JOIN hashs h ON p.hash_id = h.id
                WHERE h.side_id = %s
            """
            try:
                total_keywords_result = execute_query(total_keywords_query, (side_id,), fetch="one")
                total_keywords = total_keywords_result[0] if total_keywords_result else 0
            except Exception as query_error:
                logger.error(f"Error executing total keywords query: {query_error}")
                total_keywords = len(keywords_data) if keywords_data else 0
            
            keywords = []
            if keywords_data:
                for row in keywords_data:
                    keyword_id = row[0]
                    keyword_bytes = row[2]
                    try:
                        if keyword_bytes:
                            word_ids = unpack_int_list(keyword_bytes)
                            if word_ids and isinstance(word_ids, list):
                                # Batch load words
                                if word_ids:
                                    placeholders = ','.join(['%s'] * len(word_ids))
                                    words_query = f"SELECT id, word FROM words WHERE id IN ({placeholders})"
                                    words_result = execute_query(words_query, list(word_ids))
                                    if words_result:
                                        word_dict = {row[0]: row[1] for row in words_result}
                                        words = [word_dict.get(wid, '') for wid in word_ids if wid in word_dict]
                                        if words:
                                            keyword_text = ' '.join(words)
                                            keywords.append({
                                                'id': keyword_id,
                                                'name': keyword_text,
                                                'category_id': row[1],
                                                'file_count': row[3] or 0
                                            })
                    except Exception as e:
                        logger.warning(f"Error unpickling keyword {keyword_id}: {e}")
            
            # Calculate pagination
            total_categories_pages = (total_categories + limit - 1) // limit if total_categories > 0 else 1
            total_keywords_pages = (total_keywords + limit - 1) // limit if total_keywords > 0 else 1
            
            return jsonify({
                'success': True,
                'categories': categories,
                'keywords': keywords,
                'pagination': {
                    'categories': {
                        'total': total_categories,
                        'page': page,
                        'per_page': limit,
                        'total_pages': total_categories_pages,
                        'has_prev': page > 1,
                        'has_next': page < total_categories_pages
                    },
                    'keywords': {
                        'total': total_keywords,
                        'page': page,
                        'per_page': limit,
                        'total_pages': total_keywords_pages,
                        'has_prev': page > 1,
                        'has_next': page < total_keywords_pages
                    }
                }
            })
            
        except Exception as e:
            logger.error(f"Error fetching side categories/keywords: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return client_error(e, subsystem='Api.routes.archives', success_key='success', status=500)