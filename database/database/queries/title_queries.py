"""SQL queries for titles_content table"""
from .base_queries import BaseQueries


class TitleQueries(BaseQueries):
    """SQL queries related to titles"""
    @staticmethod
    def insert_title() -> str:
        """Insert title"""
        return """
            INSERT INTO titles_content (title_data, title_status, title_content_id, path_id)
            VALUES (%s, %s, %s, %s)
            RETURNING id
        """
    @staticmethod
    def check_title_exists() -> str:
        return """
            SELECT id FROM titles_content 
            WHERE path_id = %s AND title_status = %s 
            LIMIT 1
        """
    @staticmethod
    def select_by_path() -> str:
        return """
            SELECT title_data FROM titles_content WHERE path_id = %s
        """
    @staticmethod
    def select_by_id() -> str:
        return """
            SELECT id, title_data, title_status, path_id
            FROM titles_content
            WHERE id = %s
        """