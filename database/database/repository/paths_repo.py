import json

from .best_repo import BaseRepository
from datetime import date
from ..queries.path_queries import FileQueries

class PathsRepository(BaseRepository):

    def insert_info_paths(
        self,
        file_name,
        file_path,
        file_size,
        file_type,
        file_status="Unread",
        hash_id=None,
        file_date=None,
        date_creation=date.today(),
        coordinates="",
        extraction_provenance=None,
        processing_status="discovered",
        status_detail=None,
        attempts=0
    ):
        """Insert a new file path and return its ID.

        ``extraction_provenance`` is a JSON-serialisable mapping describing how
        each extractor derived its data (engine, version, confidence, whether
        the text is derived rather than authored). ``None`` means the file was
        ingested before provenance was captured.
        """
        params = (
            file_name,
            file_path,
            file_size,
            file_type,
            file_status,
            file_date,
            hash_id,
            date_creation,
            coordinates,
            json.dumps(extraction_provenance) if extraction_provenance is not None else None,
            processing_status,
            status_detail,
            attempts,
        )
        # Don't use commit=True in transaction context - let transaction manager handle commits
        # commit parameter is ignored when _connection is set (transaction context)
        return self.execute(
            FileQueries.insert_path(),
            params
        )

    def update_lineage(self, path_id, parent_path_id, hierarchy_path):
        """Link an extracted child to its container (PARENT-01)."""
        return self.execute(
            FileQueries.update_lineage(),
            (parent_path_id, hierarchy_path, path_id)
        )

    def get_lineage(self, path_id):
        """(file_name, hierarchy_path) for a path, or None."""
        return self.execute(
            FileQueries.get_lineage(),
            (path_id,),
            fetchone=True
        )

    def get_file_by_id(self, path_id):
        """Get full file information by ID"""
        return self.execute(
            FileQueries.get_file_by_id(),
            (path_id,),
            fetchone=True
        )

    def select_info_paths(self):
        """Get all paths"""
        return self.execute(
            FileQueries.get_all(),
            None,
            fetchall=True
        )

    def search_files(
        self,
        name=None,
        file_type=None,
        source_id=None,
        side_id=None,
        date_from=None,
        date_to=None,
        limit=50
        ):
        """Search files with filters"""
        name_param = f"%{name}%" if name else None

        params = (
            name, name_param,
            file_type, file_type,
            source_id, source_id,
            side_id, side_id,
            date_from, date_from,
            date_to, date_to,
            limit
        )

        return self.execute(
            FileQueries.search_files(),
            params,
            fetchall=True
        )

    def get_recent_files(self, limit=10):
        """Get most recent files"""
        return self.execute(
            FileQueries.get_recent_files(),
            (limit,),
            fetchall=True
        )

    def search_files_by_word_count(self, word):
        """Return count of files containing a word"""
        row = self.execute(
            FileQueries.search_files_by_word_count(),
            (f"%{word}%",),
            fetchone=True
        )
        return row[0] if row else 0

    def search_files_by_word(self, word, limit=50, offset=0):
        """Search files by word content"""
        return self.execute(
            FileQueries.search_files_by_word(),
            (f"%{word}%", limit, offset),
            fetchall=True
        )

    def get_file_word_count(self, path_id):
        """Count distinct words in a file"""
        row = self.execute(
            FileQueries.get_file_word_count(),
            (path_id,),
            fetchone=True
        )
        return row[0] if row else 0

    def update_file_status(self, path_id, status):
        """Update file status"""
        return self.execute(
            FileQueries.update_file_status(),
            (status, path_id)
        )

    def check_file_processed(self, file_path):
        """Check if file already processed"""
        row = self.execute(
            FileQueries.check_file_processed(),
            (file_path,),
            fetchone=True
        )
        return row is not None
    
    def get_path_id_by_hash_id(self, hash_id):
        """Get path ID by hash ID"""
        row = self.execute(
            FileQueries.get_path_id_by_hash_id(),
            (hash_id,),
            fetchone=True
        )
        return row[0] if row else None