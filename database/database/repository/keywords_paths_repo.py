from .best_repo import BaseRepository
from ..queries.keyword_path_queries import KeywordPathQueries

class KeywordsPathsRepository(BaseRepository):


    def bulk_insert_keywords_paths(self, path_id, keyword_id_and_counts):#{id:count}

        if not keyword_id_and_counts:
            return        
        values = [(path_id, keyword_id, count) for keyword_id, count in keyword_id_and_counts.items()]# [(path_id, keyword_id, count),(path_id, keyword_id, count),(path_id, keyword_id, count)]
        placeholders = ",".join(["(%s,%s,%s)"] * len(values))
        query = KeywordPathQueries.insert_keyword_path(placeholders)

        flat_values = [item for sublist in values for item in sublist]# [path_id, keyword_id, count,path_id, keyword_id, count,path_id, keyword_id, count]
        self.execute(query, flat_values)

    def insert_keywords_paths(self, path_id, keyword_id, word_count):
        
        query = KeywordPathQueries.insert_keyword_path()
        params = (path_id, keyword_id, word_count)

        return self.execute(query, params, True)
    

    
    

