from .best_repo import BaseRepository
from ..queries.hash_queries import HashQueries

class HashsRepository(BaseRepository):

    def insert_info_hashs(self, hash_value, source_id, side_id):
        """Insert or update a hash record and return its ID"""
        # Don't use commit=True in transaction context - let transaction manager handle commits
        # commit parameter is ignored when _connection is set (transaction context)
        return self.execute(
            HashQueries.insert_hash(),
            (hash_value, source_id, side_id)
        )
    
    def select_hashs(self):
        """Return all hashes with their source IDs"""
        return self.execute(
            HashQueries.get_all(),
            None,
            fetchall=True
        )
    

    def hash_exists(self, hash_value, source_id, side_id) -> bool:
        """Check if hash already exists and is linked to a path"""
        row = self.execute(
            HashQueries.check_hash_exists(),
            (hash_value, source_id, side_id),
            fetchone=True
        )
        return row is not None
    
    def get_hash_records(self, hash_value):
        """Get all records related to a hash value"""
        return self.execute(
            HashQueries.get_hash_records(),
            (hash_value,),
            fetchone=True
        )

    def get_hash_by_id(self, hash_id):
        """Return hash string by hash ID"""
        row = self.execute(
            HashQueries.get_hash_by_id(),
            (hash_id,),
            fetchone=True
        )
        return row[0] if row else None

    def check_duplicate(self, hash_value, source_id, side_id):
        """Check for duplicate file"""
        row = self.execute(
            HashQueries.check_duplicate(),
            (hash_value, source_id, side_id),
            fetchone=True
        )
        return row[0] if row else None
    
    def check_hash_exists_for_source(self, hash_value, source_id):
        """Check if hash exists for given source (any side)"""
        row = self.execute(
            HashQueries.check_hash_exists_for_source(),
            (hash_value, source_id),
            fetchone=True
        )
        return row is not None
    