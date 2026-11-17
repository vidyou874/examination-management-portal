from functools import wraps
from flask import session, redirect, url_for, flash, abort, request
from app.database import get_db

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('auth.login', next=request.path))
        return f(*args, **kwargs)
    return decorated_function

def role_required(*allowed_roles):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_id' not in session:
                flash('Please log in to continue.', 'warning')
                return redirect(url_for('auth.login', next=request.path))
            
            user_role = session.get('role')
            if user_role not in allowed_roles:
                flash('Access denied: You do not have permission to view this resource.', 'danger')
                abort(403)
            
            # Additional verification against the database for account state and examiner approval
            db = get_db()
            user = db.execute(
                "SELECT id, role, is_active FROM users WHERE id = ?",
                (session['user_id'],)
            ).fetchone()

            if not user or not user['is_active']:
                session.clear()
                flash('Your account has been deactivated. Please contact the administrator.', 'danger')
                return redirect(url_for('auth.login'))

            if user['role'] == 'examiner':
                profile = db.execute(
                    "SELECT approval_status FROM examiner_profiles WHERE user_id = ?",
                    (user['id'],)
                ).fetchone()
                if not profile or profile['approval_status'] != 'approved':
                    flash('Your examiner account is currently pending administrator approval or inactive.', 'warning')
                    return redirect(url_for('auth.pending_approval'))

            return f(*args, **kwargs)
        return decorated_function
    return decorator
