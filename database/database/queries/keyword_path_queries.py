"""SQL queries for keywords_paths table"""
from .base_queries import BaseQueries

class KeywordPathQueries(BaseQueries):
    """SQL queries for keyword-path relationships"""
    
    @staticmethod
    def insert_keyword_path(placeholders = "(%s,%s,%s)") -> str:
        """Insert keyword-path relationship"""
        return f"""
            INSERT INTO keywords_paths (path_id, keyword_id, word_count)
            VALUES {placeholders}
            ON CONFLICT (path_id, keyword_id) 
            DO UPDATE SET word_count = EXCLUDED.word_count
        """
    
    @staticmethod
    def batch_insert_keyword_paths() -> str:
        """Batch insert keyword-path relationships"""
        return """
            INSERT INTO keywords_paths (path_id, keyword_id, word_count)
            VALUES %s
            ON CONFLICT (path_id, keyword_id)
            DO UPDATE SET word_count = EXCLUDED.word_count
        """
