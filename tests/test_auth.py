import pytest
from app.database import get_db

def test_admin_created_programmatically(app):
    """FR-AUTH-03: Administrator account must be created programmatically during initialization."""
    with app.app_context():
        db = get_db()
        admin = db.execute("SELECT * FROM users WHERE role = 'admin'").fetchone()
        assert admin is not None
        assert admin['username'] == 'admin'
        assert admin['email'] == 'admin@emp.edu'
        assert admin['password_hash'] != 'Admin@123'  # Must be hashed!

def test_student_registration_and_login(client, app):
    """FR-AUTH-01 & FR-AUTH-02: Student can register and log in."""
    res = client.post('/register/student', data={
        'username': 'new_student',
        'email': 'new_stu@univ.edu',
        'password': 'Password@123',
        'confirm_password': 'Password@123',
        'student_id_number': 'STU999',
        'full_name': 'New Student',
        'department': 'CSE',
        'program': 'B.Tech'
    }, follow_redirects=True)
    assert res.status_code == 200
    assert b"Registration successful" in res.data

    # Login
    login_res = client.post('/login', data={
        'username_or_email': 'new_student',
        'password': 'Password@123'
    }, follow_redirects=True)
    assert login_res.status_code == 200
    assert b"Student Portal" in login_res.data

def test_examiner_pending_approval_lockdown(client, app):
    """FR-AUTH-04 & FR-AUTH-05: Pending examiner cannot access protected examiner features."""
    client.post('/register/examiner', data={
        'username': 'pending_fac',
        'email': 'fac@univ.edu',
        'password': 'Password@123',
        'confirm_password': 'Password@123',
        'employee_id': 'FAC999',
        'full_name': 'Dr. Pending',
        'department': 'IT',
        'designation': 'Assistant Prof'
    }, follow_redirects=True)

    # Attempt login while pending
    login_res = client.post('/login', data={
        'username_or_email': 'pending_fac',
        'password': 'Password@123'
    }, follow_redirects=True)
    assert login_res.status_code == 200
    assert b"Approval Pending" in login_res.data

    # Direct access to examiner dashboard should be blocked
    dash_res = client.get('/examiner/dashboard', follow_redirects=True)
    assert b"Please log in" in dash_res.data or b"Approval Pending" in dash_res.data

def test_role_isolation_enforcement(client, app, sample_setup):
    """BR-01: Role isolation enforced on backend (403 for unauthorized access)."""
    # Login as student
    client.post('/login', data={'username_or_email': 'st_test', 'password': 'Pass@123'}, follow_redirects=True)

    # Student trying to access admin dashboard -> 403 Forbidden
    res_admin = client.get('/admin/dashboard')
    assert res_admin.status_code == 403

    # Student trying to access examiner dashboard -> 403 Forbidden
    res_examiner = client.get('/examiner/dashboard')
    assert res_examiner.status_code == 403
