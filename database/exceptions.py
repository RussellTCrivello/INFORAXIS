"""
Database exceptions for error handling
"""


class QueryError(Exception):
    """Raised when a database query fails"""
    pass


class TransactionError(Exception):
    """Raised when a database transaction fails"""
    pass
