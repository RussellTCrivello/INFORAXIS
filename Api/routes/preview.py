"""
File Preview Routes
Handles in-browser file preview for images, PDFs, and documents
"""

from flask import Blueprint, request, jsonify, send_file
from Api.services.file_preview import FilePreviewService
import logging

logger = logging.getLogger(__name__)

preview_bp = Blueprint('preview', __name__, url_prefix='/api/preview')


@preview_bp.route('/<int:file_id>', methods=['GET'])
def get_file_preview(file_id):
    """
    Get file preview for in-browser viewing.
    
    Query Parameters:
    - max_width: Maximum preview width in pixels (default: 1200)
    - max_height: Maximum preview height in pixels (default: 800)
    
    Returns:
    JSON response with preview data or error message
    """
    try:
        max_width = int(request.args.get('max_width', 1200))
        max_height = int(request.args.get('max_height', 800))
        
        preview_data = FilePreviewService.get_preview(
            file_id=file_id,
            max_width=max_width,
            max_height=max_height
        )
        
        return jsonify(preview_data)
        
    except Exception as e:
        # SEC-08: client-safe error, details logged server-side only.
        from core.errors import client_error
        return client_error(e, subsystem="preview",
                            public_message="Preview generation failed")


def register_preview_routes(app):
    """Register preview routes with the Flask app"""
    app.register_blueprint(preview_bp)

