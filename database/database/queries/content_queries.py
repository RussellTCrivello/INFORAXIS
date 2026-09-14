"""SQL queries for contents table"""
from .base_queries import BaseQueries


class ContentQueries(BaseQueries):
    """SQL queries related to content"""
    
    @staticmethod
    def insert_content() -> str:
        """Insert content chunk"""
        return """
            INSERT INTO contents (content_data, content_date, path_id)
            VALUES (%s, %s, %s)
            RETURNING id
        """
    
    @staticmethod
    def get_content_chunks() -> str:
        """Get content chunks for a file"""
        return """
            SELECT id, content_data, content_date
            FROM contents
            WHERE path_id = %s
            LIMIT %s
        """
    
    @staticmethod
    def get_content_count() -> str:
        """Count content chunks"""
        return "SELECT COUNT(*) FROM contents WHERE path_id = %s"
    
    @staticmethod
    def load_content() -> str:
        """Load all content for a file"""
        return """
            SELECT id, content_data 
            FROM contents 
            WHERE path_id=%s 
            ORDER BY id
        """
    
    @staticmethod
    def get_content_stats() -> str:
        """Get content statistics"""
        return """
            SELECT 
                COUNT(*) as chunk_count,
                SUM(LENGTH(content_data)) as total_bytes
            FROM contents 
            WHERE path_id = %s
        """
    
    @staticmethod
    def delete_content() -> str:
        """Delete all content for a file"""
        return "DELETE FROM contents WHERE path_id = %s"
    # ------------------------------------------------------------------
    # Raw (structured) content - the display-fidelity store. See
    # migration m0010 for the rationale.
    # ------------------------------------------------------------------

    @staticmethod
    def insert_raw_content() -> str:
        """Insert one raw-content chunk"""
        return """
            INSERT INTO contents_raw (path_id, chunk_seq, content, char_count)
            VALUES (%s, %s, %s, %s)
        """

    @staticmethod
    def load_raw_content() -> str:
        """Load all raw-content chunks for a file, in order"""
        return """
            SELECT content
            FROM contents_raw
            WHERE path_id = %s
            ORDER BY chunk_seq
        """

    @staticmethod
    def delete_raw_content() -> str:
        """Delete all raw content for a file"""
        return "DELETE FROM contents_raw WHERE path_id = %s"
