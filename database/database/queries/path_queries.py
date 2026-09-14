from .base_queries import BaseQueries

class FileQueries(BaseQueries):
    """SQL queries related to files/paths"""
    
    @staticmethod
    def get_file_by_id() -> str:
        """Get complete file information by ID"""
        return """
            SELECT p.id, p.file_name, p.file_path, p.file_size, p.file_type,
                   p.file_status, p.file_date, p.date_creation, p.hash_id,
                   h.source_id, h.side_id,
                   s.name as source_name, si.name as side_name
            FROM paths p
            LEFT JOIN hashs h ON p.hash_id = h.id
            LEFT JOIN sources s ON h.source_id = s.id
            LEFT JOIN sides si ON h.side_id = si.id
            WHERE p.id = %s
        """
    @staticmethod
    def get_all() -> str:
        return "SELECT * FROM paths"
    
    @staticmethod
    def search_files() -> str:
        """Search files with multiple filter criteria"""
        return """
            SELECT p.id, p.file_name, p.file_path, p.file_size, p.file_type,
                   p.file_status, p.file_date, p.date_creation, p.hash_id,
                   h.source_id, h.side_id,
                   s.name as source_name, si.name as side_name
            FROM paths p
            LEFT JOIN hashs h ON p.hash_id = h.id
            LEFT JOIN sources s ON h.source_id = s.id
            LEFT JOIN sides si ON h.side_id = si.id
            WHERE 1=1
              AND (%s IS NULL OR p.file_name ILIKE %s)
              AND (%s IS NULL OR p.file_type = %s)
              AND (%s IS NULL OR h.source_id = %s)
              AND (%s IS NULL OR h.side_id = %s)
              AND (%s IS NULL OR p.file_date >= %s)
              AND (%s IS NULL OR p.file_date <= %s)
            ORDER BY p.date_creation DESC
            LIMIT %s
        """
    
    @staticmethod
    def get_recent_files() -> str:
        """Get most recently created files"""
        return """
            SELECT p.id, p.file_name, p.file_path, p.file_size, p.file_type,
                   p.file_status, p.file_date, p.date_creation, p.hash_id,
                   h.source_id, h.side_id,
                   s.name as source_name, si.name as side_name
            FROM paths p
            LEFT JOIN hashs h ON p.hash_id = h.id
            LEFT JOIN sources s ON h.source_id = s.id
            LEFT JOIN sides si ON h.side_id = si.id
            ORDER BY p.date_creation DESC
            LIMIT %s
        """
    
    @staticmethod
    def search_files_by_word_count() -> str:
        """Count files containing search word"""
        return """
            SELECT COUNT(DISTINCT p.id)
            FROM paths p
            JOIN words_paths wp ON p.id = wp.path_id
            JOIN words w ON wp.word_id = w.id
            WHERE w.word ILIKE %s
        """
    
    @staticmethod
    def search_files_by_word() -> str:
        """Search files by word content with pagination"""
        return """
            SELECT DISTINCT ON (p.id) 
                   p.id, p.file_name, p.file_type, p.file_date,
                   COALESCE(s.name, 'Unknown') as source_name, 
                   COALESCE(si.name, 'Unknown') as side_name,
                   COUNT(wp.word_id) OVER (PARTITION BY p.id) as match_count
            FROM paths p
            LEFT JOIN hashs h ON p.hash_id = h.id
            LEFT JOIN sources s ON h.source_id = s.id
            LEFT JOIN sides si ON h.side_id = si.id
            JOIN words_paths wp ON p.id = wp.path_id
            JOIN words w ON wp.word_id = w.id
            WHERE w.word ILIKE %s
            ORDER BY p.id, match_count DESC
            LIMIT %s OFFSET %s
        """
    
    @staticmethod
    def get_file_word_count() -> str:
        """Count distinct words in a file"""
        return """
            SELECT COUNT(DISTINCT wp.word_id)
            FROM words_paths wp
            WHERE wp.path_id = %s
        """
    
    @staticmethod
    def insert_path() -> str:
        """Insert file path with conflict handling"""
        return """
            INSERT INTO paths
            (file_name, file_path, file_size, file_type, file_status, file_date, hash_id, date_creation, coordinates, extraction_provenance, processing_status, status_detail, attempts, status_updated_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s,NOW())
            RETURNING id;
        """
    
    @staticmethod
    def update_file_status() -> str:
        """Update file processing status"""
        return "UPDATE paths SET file_status = %s WHERE id = %s"

    @staticmethod
    def update_lineage() -> str:
        """Link an extracted child to the container it came from.

        parent_path_id is the queryable relationship; hierarchy_path is the
        human-readable archive::child::grandchild chain. Both are set together
        so they cannot drift apart.
        """
        return (
            "UPDATE paths SET parent_path_id = %s, hierarchy_path = %s,"
            " status_updated_at = NOW() WHERE id = %s"
        )

    @staticmethod
    def get_lineage() -> str:
        """Read a path's lineage, used to build a child's hierarchy_path."""
        return "SELECT file_name, hierarchy_path FROM paths WHERE id = %s"
    
    @staticmethod
    def check_file_processed() -> str:
        """Check if file has been processed"""
        return "SELECT id FROM paths WHERE file_path = %s AND file_status = 'Read'"
    
    @staticmethod
    def get_path_id_by_hash_id() -> str:
        """Get path ID by hash ID"""
        return "SELECT id FROM paths WHERE hash_id = %s LIMIT 1"