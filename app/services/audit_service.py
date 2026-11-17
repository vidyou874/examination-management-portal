from app.database import get_db

def log_audit(action, entity_type, entity_id=None, details=None, user_id=None, ip_address=None):
    """
    Records an auditable event in the audit_logs table.
    """
    db = get_db()
    cursor = db.cursor()
    cursor.execute(
        """
        INSERT INTO audit_logs (user_id, action, entity_type, entity_id, details, ip_address)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (user_id, action, entity_type, entity_id, details, ip_address)
    )
    db.commit()
    return cursor.lastrowid

def get_audit_logs(limit=100, entity_type=None, action=None, search=None):
    """
    Retrieves audit logs with optional filtering.
    """
    db = get_db()
    query = """
        SELECT a.*, u.username, u.role
        FROM audit_logs a
        LEFT JOIN users u ON a.user_id = u.id
        WHERE 1=1
    """
    params = []
    if entity_type:
        query += " AND a.entity_type = ?"
        params.append(entity_type)
    if action:
        query += " AND a.action = ?"
        params.append(action)
    if search:
        query += " AND (a.details LIKE ? OR a.action LIKE ? OR u.username LIKE ?)"
        wildcard = f"%{search}%"
        params.extend([wildcard, wildcard, wildcard])

    query += " ORDER BY a.created_at DESC LIMIT ?"
    params.append(limit)

    return db.execute(query, params).fetchall()
