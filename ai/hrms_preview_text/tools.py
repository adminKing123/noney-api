from langchain.tools import tool
from .utils import find_user_local

@tool
def get_a_user(query: str) -> dict:
    """
    Search user by:
    - name (partial, case-insensitive)
    - user_id (exact)
    - employee_id (exact)

    returns
    - user_id
    - employee_id
    - name
    - signed_array
    """
    return find_user_local(query)