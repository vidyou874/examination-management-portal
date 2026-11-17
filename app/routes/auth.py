from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from app.services.auth_service import authenticate_user, register_student, register_examiner, get_examiner_profile, get_student_profile

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_id' in session:
        role = session.get('role')
        if role == 'admin':
            return redirect(url_for('admin.dashboard'))
        elif role == 'examiner':
            return redirect(url_for('examiner.dashboard'))
        elif role == 'student':
            return redirect(url_for('student.dashboard'))

    if request.method == 'POST':
        username_or_email = request.form.get('username_or_email', '')
        password = request.form.get('password', '')

        user, err = authenticate_user(username_or_email, password)
        if err:
            flash(err, 'danger')
            return render_template('auth/login.html')

        # Check examiner approval status
        if user['role'] == 'examiner':
            profile = get_examiner_profile(user['id'])
            if profile and profile['approval_status'] == 'pending':
                session['temp_user_id'] = user['id']
                session['temp_role'] = 'examiner'
                return redirect(url_for('auth.pending_approval'))

        # Set session
        session.clear()
        session['user_id'] = user['id']
        session['username'] = user['username']
        session['role'] = user['role']

        flash(f'Welcome back, {user["username"]}!', 'success')
        next_url = request.args.get('next')
        if next_url and next_url.startswith('/'):
            return redirect(next_url)

        if user['role'] == 'admin':
            return redirect(url_for('admin.dashboard'))
        elif user['role'] == 'examiner':
            return redirect(url_for('examiner.dashboard'))
        elif user['role'] == 'student':
            return redirect(url_for('student.dashboard'))

    return render_template('auth/login.html')

@auth_bp.route('/register/student', methods=['GET', 'POST'])
def register_student_route():
    if request.method == 'POST':
        username = request.form.get('username', '')
        email = request.form.get('email', '')
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')
        student_id_number = request.form.get('student_id_number', '')
        full_name = request.form.get('full_name', '')
        department = request.form.get('department', '')
        program = request.form.get('program', '')
        phone = request.form.get('phone', '')

        if not (username and email and password and student_id_number and full_name and department and program):
            flash('All required fields must be completed.', 'warning')
            return render_template('auth/register_student.html')

        if password != confirm_password:
            flash('Passwords do not match.', 'danger')
            return render_template('auth/register_student.html')

        user_id, err = register_student(username, email, password, student_id_number, full_name, department, program, phone)
        if err:
            flash(err, 'danger')
            return render_template('auth/register_student.html')

        flash('Registration successful! You may now log in.', 'success')
        return redirect(url_for('auth.login'))

    return render_template('auth/register_student.html')

@auth_bp.route('/register/examiner', methods=['GET', 'POST'])
def register_examiner_route():
    if request.method == 'POST':
        username = request.form.get('username', '')
        email = request.form.get('email', '')
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')
        employee_id = request.form.get('employee_id', '')
        full_name = request.form.get('full_name', '')
        department = request.form.get('department', '')
        designation = request.form.get('designation', '')
        phone = request.form.get('phone', '')

        if not (username and email and password and employee_id and full_name and department and designation):
            flash('All required fields must be completed.', 'warning')
            return render_template('auth/register_examiner.html')

        if password != confirm_password:
            flash('Passwords do not match.', 'danger')
            return render_template('auth/register_examiner.html')

        user_id, err = register_examiner(username, email, password, employee_id, full_name, department, designation, phone)
        if err:
            flash(err, 'danger')
            return render_template('auth/register_examiner.html')

        flash('Examiner registration submitted successfully! Your account is pending administrator approval before you can access the portal.', 'info')
        return redirect(url_for('auth.pending_approval'))

    return render_template('auth/register_examiner.html')

@auth_bp.route('/pending-approval')
def pending_approval():
    return render_template('auth/pending_approval.html')

@auth_bp.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out securely.', 'info')
    return redirect(url_for('auth.login'))
