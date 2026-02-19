from flask import Blueprint, request, jsonify
from ai.hrms_preview_text.utils import get_employees_table

hrms_bp = Blueprint('hrms', __name__, url_prefix='/hrms')

@hrms_bp.route('/employees', methods=['GET'])
def employees_table_view():
    """
    Returns a paginated table view of all employees.
    Query params:
        - page: int (default=1)
        - limit: int (default=10)
        - search: str (default="")
    """
    page = int(request.args.get('page', 1))
    limit = int(request.args.get('limit', 10))
    search = request.args.get('search', '')
    data = get_employees_table(page=page, limit=limit, search=search)
    return jsonify(data)
