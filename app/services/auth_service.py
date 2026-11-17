from werkzeug.security import generate_password_hash, check_password_hash
from app.database import get_db
from app.services.audit_service import log_audit

def authenticate_user(username_or_email, password):
    """
    Authenticates a user by username or email.
    Returns (user_row, error_message).
    """
    db = get_db()
    user = db.execute(
        """
        SELECT * FROM users 
        WHERE (username = ? OR email = ?)
        """,
        (username_or_email.strip(), username_or_email.strip().lower())
    ).fetchone()

    if not user:
        return None, "Invalid username or password."

    if not check_password_hash(user['password_hash'], password):
        return None, "Invalid username or password."

    if not user['is_active']:
        return None, "Your account has been deactivated. Please contact an administrator."

    # If examiner, check approval status
    if user['role'] == 'examiner':
        profile = db.execute(
            "SELECT approval_status FROM examiner_profiles WHERE user_id = ?",
            (user['id'],)
        ).fetchone()
        if profile and profile['approval_status'] == 'rejected':
            return None, "Your examiner registration was rejected by the administrator."

    return user, None

def register_student(username, email, password, student_id_number, full_name, department, program, phone=None):
    """
    Registers a new student and student profile in a single transaction.
    Returns (user_id, error_message).
    """
    db = get_db()
    username = username.strip()
    email = email.strip().lower()
    student_id_number = student_id_number.strip().upper()

    # Pre-checks
    existing = db.execute(
        "SELECT id FROM users WHERE username = ? OR email = ?",
        (username, email)
    ).fetchone()
    if existing:
        return None, "Username or email is already registered."

    existing_sid = db.execute(
        "SELECT id FROM student_profiles WHERE student_id_number = ?",
        (student_id_number,)
    ).fetchone()
    if existing_sid:
        return None, "Student ID Number is already registered."

    password_hash = generate_password_hash(password)

    try:
        cursor = db.cursor()
        cursor.execute("BEGIN IMMEDIATE;")
        cursor.execute(
            """
            INSERT INTO users (username, email, password_hash, role, is_active)
            VALUES (?, ?, ?, 'student', 1)
            """,
            (username, email, password_hash)
        )
        user_id = cursor.lastrowid

        cursor.execute(
            """
            INSERT INTO student_profiles (user_id, student_id_number, full_name, department, program, phone)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (user_id, student_id_number, full_name.strip(), department.strip(), program.strip(), phone)
        )
        db.commit()

        log_audit(
            action="STUDENT_REGISTER",
            entity_type="users",
            entity_id=user_id,
            details=f"Student registered: {username} ({student_id_number})",
            user_id=user_id
        )
        return user_id, None
    except Exception as e:
        db.rollback()
        return None, f"Registration failed: {str(e)}"

def register_examiner(username, email, password, employee_id, full_name, department, designation, phone=None):
    """
    Registers a new examiner pending administrator approval.
    Returns (user_id, error_message).
    """
    db = get_db()
    username = username.strip()
    email = email.strip().lower()
    employee_id = employee_id.strip().upper()

    existing = db.execute(
        "SELECT id FROM users WHERE username = ? OR email = ?",
        (username, email)
    ).fetchone()
    if existing:
        return None, "Username or email is already registered."

    existing_eid = db.execute(
        "SELECT id FROM examiner_profiles WHERE employee_id = ?",
        (employee_id,)
    ).fetchone()
    if existing_eid:
        return None, "Employee ID is already registered."

    password_hash = generate_password_hash(password)

    try:
        cursor = db.cursor()
        cursor.execute("BEGIN IMMEDIATE;")
        cursor.execute(
            """
            INSERT INTO users (username, email, password_hash, role, is_active)
            VALUES (?, ?, ?, 'examiner', 1)
            """,
            (username, email, password_hash)
        )
        user_id = cursor.lastrowid

        cursor.execute(
            """
            INSERT INTO examiner_profiles (user_id, employee_id, full_name, department, designation, phone, approval_status)
            VALUES (?, ?, ?, ?, ?, ?, 'pending')
            """,
            (user_id, employee_id, full_name.strip(), department.strip(), designation.strip(), phone)
        )
        db.commit()

        log_audit(
            action="EXAMINER_REGISTER",
            entity_type="users",
            entity_id=user_id,
            details=f"Examiner registered (pending approval): {username} ({employee_id})",
            user_id=user_id
        )
        return user_id, None
    except Exception as e:
        db.rollback()
        return None, f"Registration failed: {str(e)}"

def get_examiner_profile(user_id):
    db = get_db()
    return db.execute(
        """
        SELECT u.id, u.username, u.email, u.is_active, ep.*
        FROM users u
        JOIN examiner_profiles ep ON u.id = ep.user_id
        WHERE u.id = ?
        """,
        (user_id,)
    ).fetchone()

def get_student_profile(user_id):
    db = get_db()
    return db.execute(
        """
        SELECT u.id, u.username, u.email, u.is_active, sp.*
        FROM users u
        JOIN student_profiles sp ON u.id = sp.user_id
        WHERE u.id = ?
        """,
        (user_id,)
    ).fetchone()

def update_examiner_status(user_id, new_status, admin_user_id):
    """
    Approves or rejects an examiner account.
    """
    if new_status not in ('approved', 'rejected', 'pending'):
        return False, "Invalid status."

    db = get_db()
    try:
        db.execute(
            """
            UPDATE examiner_profiles
            SET approval_status = ?, approved_at = CURRENT_TIMESTAMP, approved_by = ?
            WHERE user_id = ?
            """,
            (new_status, admin_user_id, user_id)
        )
        db.commit()

        log_audit(
            action=f"EXAMINER_STATUS_{new_status.upper()}",
            entity_type="examiner_profiles",
            entity_id=user_id,
            details=f"Examiner status updated to {new_status} by admin {admin_user_id}",
            user_id=admin_user_id
        )
        return True, None
    except Exception as e:
        db.rollback()
        return False, str(e)

def toggle_user_active_state(user_id, is_active, admin_user_id):
    db = get_db()
    try:
        db.execute(
            "UPDATE users SET is_active = ? WHERE id = ?",
            (1 if is_active else 0, user_id)
        )
        db.commit()
        state_str = "ACTIVATED" if is_active else "DEACTIVATED"
        log_audit(
            action=f"USER_{state_str}",
            entity_type="users",
            entity_id=user_id,
            details=f"User {user_id} {state_str.lower()} by admin",
            user_id=admin_user_id
        )
        return True, None
    except Exception as e:
        db.rollback()
        return False, str(e)

def list_examiners(approval_status=None, search=None):
    db = get_db()
    query = """
        SELECT u.id, u.username, u.email, u.is_active, u.created_at,
               ep.employee_id, ep.full_name, ep.department, ep.designation, 
               ep.phone, ep.approval_status, ep.approved_at
        FROM users u
        JOIN examiner_profiles ep ON u.id = ep.user_id
        WHERE u.role = 'examiner'
    """
    params = []
    if approval_status:
        query += " AND ep.approval_status = ?"
        params.append(approval_status)
    if search:
        query += " AND (ep.full_name LIKE ? OR ep.employee_id LIKE ? OR u.email LIKE ?)"
        wildcard = f"%{search}%"
        params.extend([wildcard, wildcard, wildcard])

    query += " ORDER BY ep.approval_status = 'pending' DESC, u.created_at DESC"
    return db.execute(query, params).fetchall()

def list_students(search=None):
    db = get_db()
    query = """
        SELECT u.id, u.username, u.email, u.is_active, u.created_at,
               sp.student_id_number, sp.full_name, sp.department, sp.program, sp.phone
        FROM users u
        JOIN student_profiles sp ON u.id = sp.user_id
        WHERE u.role = 'student'
    """
    params = []
    if search:
        query += " AND (sp.full_name LIKE ? OR sp.student_id_number LIKE ? OR u.email LIKE ?)"
        wildcard = f"%{search}%"
        params.extend([wildcard, wildcard, wildcard])

    query += " ORDER BY sp.student_id_number ASC"
    return db.execute(query, params).fetchall()
