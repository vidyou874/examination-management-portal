import sqlite3
import os
from flask import g, current_app
from werkzeug.security import generate_password_hash

def get_db(db_path=None):
    """
    Returns an active SQLite connection with row factory and foreign keys enabled.
    Stores connection in Flask's g when in application context.
    """
    if db_path is None:
        try:
            db_path = current_app.config['DATABASE_PATH']
        except RuntimeError:
            from app.config import Config
            db_path = Config.DATABASE_PATH

    # If within request context and using default app db_path
    try:
        if 'db' not in g:
            # Ensure directory exists for file-based DB
            if db_path != ':memory:':
                os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
            
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON;")
            g.db = conn
        return g.db
    except RuntimeError:
        # Outside application context (e.g., CLI or standalone script)
        if db_path != ':memory:':
            os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn

def close_db(e=None):
    """Closes the database connection if open."""
    db = g.pop('db', None)
    if db is not None:
        db.close()

def init_db(app=None, db_path=None):
    """
    Initializes the database schema and ensures the initial administrator account exists.
    """
    if app:
        with app.app_context():
            _do_init_db(app.config.get('DATABASE_PATH'), 
                        app.config.get('ADMIN_USERNAME', 'admin'),
                        app.config.get('ADMIN_EMAIL', 'admin@emp.edu'),
                        app.config.get('ADMIN_PASSWORD', 'Admin@123'))
    else:
        from app.config import Config
        path = db_path or Config.DATABASE_PATH
        _do_init_db(path, Config.ADMIN_USERNAME, Config.ADMIN_EMAIL, Config.ADMIN_PASSWORD)

def _do_init_db(db_path, admin_user, admin_email, admin_pass):
    schema_path = os.path.join(os.path.dirname(__file__), 'schema.sql')
    with open(schema_path, 'r', encoding='utf-8') as f:
        schema_sql = f.read()

    conn = get_db(db_path)
    try:
        conn.executescript(schema_sql)
        
        # Check if administrator account exists
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM users WHERE role = 'admin' LIMIT 1")
        admin_exists = cursor.fetchone()

        if not admin_exists:
            pw_hash = generate_password_hash(admin_pass)
            cursor.execute(
                """
                INSERT INTO users (username, email, password_hash, role, is_active)
                VALUES (?, ?, ?, 'admin', 1)
                """,
                (admin_user, admin_email, pw_hash)
            )
            admin_id = cursor.lastrowid
            
            # Log admin creation in audit_logs
            cursor.execute(
                """
                INSERT INTO audit_logs (user_id, action, entity_type, entity_id, details)
                VALUES (?, 'SYSTEM_INIT', 'users', ?, 'Default Administrator initialized programmatically')
                """,
                (admin_id, admin_id)
            )
        conn.commit()
    finally:
        # If outside request context, close the connection
        try:
            if 'db' not in g:
                conn.close()
        except RuntimeError:
            conn.close()
