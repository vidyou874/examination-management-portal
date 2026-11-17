from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from app.decorators import role_required
from app.database import get_db
from app.services.course_service import get_courses, get_course_by_id, create_course, update_course, delete_or_archive_course
from app.services.exam_service import (
    get_examinations, get_examination_by_id, create_examination, update_examination,
    update_exam_status, get_assigned_examiners, assign_examiner_to_exam, unassign_examiner_from_exam
)
from app.services.rubric_service import (
    get_rubrics_by_exam, add_rubric_criterion, update_rubric_criterion, delete_rubric_criterion, get_total_weightage
)
from app.services.auth_service import list_examiners, list_students, update_examiner_status, toggle_user_active_state
from app.services.slot_service import get_slots, get_slot_by_id, reassign_slot_examiner
from app.services.booking_service import get_all_bookings, admin_reschedule_booking, get_booking_events
from app.services.evaluation_service import publish_exam_results, unpublish_exam_results, get_all_evaluations_for_exam
from app.services.audit_service import get_audit_logs

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

@admin_bp.before_request
@role_required('admin')
def check_admin():
    pass

@admin_bp.route('/dashboard')
def dashboard():
    db = get_db()
    stats = {
        'total_courses': db.execute("SELECT COUNT(*) FROM courses").fetchone()[0],
        'total_exams': db.execute("SELECT COUNT(*) FROM examinations").fetchone()[0],
        'total_students': db.execute("SELECT COUNT(*) FROM users WHERE role = 'student'").fetchone()[0],
        'approved_examiners': db.execute("SELECT COUNT(*) FROM examiner_profiles WHERE approval_status = 'approved'").fetchone()[0],
        'pending_examiners': db.execute("SELECT COUNT(*) FROM examiner_profiles WHERE approval_status = 'pending'").fetchone()[0],
        'total_slots': db.execute("SELECT COUNT(*) FROM examination_slots").fetchone()[0],
        'active_bookings': db.execute("SELECT COUNT(*) FROM bookings WHERE status = 'confirmed'").fetchone()[0],
        'submitted_evaluations': db.execute("SELECT COUNT(*) FROM evaluations WHERE status = 'submitted'").fetchone()[0]
    }
    recent_exams = get_examinations()[:5]
    pending_list = list_examiners(approval_status='pending')[:5]
    recent_logs = get_audit_logs(limit=8)
    return render_template('admin/dashboard.html', stats=stats, recent_exams=recent_exams, pending_examiners=pending_list, recent_logs=recent_logs)

# ----------------- COURSES -----------------
@admin_bp.route('/courses', methods=['GET', 'POST'])
def courses():
    if request.method == 'POST':
        code = request.form.get('code')
        name = request.form.get('name')
        description = request.form.get('description')
        if not code or not name:
            flash('Course Code and Name are required.', 'warning')
        else:
            cid, err = create_course(code, name, description, session['user_id'])
            if err:
                flash(err, 'danger')
            else:
                flash(f'Course {code.upper()} created successfully.', 'success')
        return redirect(url_for('admin.courses'))

    search = request.args.get('search')
    course_list = get_courses(search=search)
    return render_template('admin/courses.html', courses=course_list, search=search)

@admin_bp.route('/courses/<int:course_id>/edit', methods=['POST'])
def edit_course(course_id):
    code = request.form.get('code')
    name = request.form.get('name')
    description = request.form.get('description')
    is_active = request.form.get('is_active') == '1'

    ok, err = update_course(course_id, code, name, description, is_active, session['user_id'])
    if err:
        flash(err, 'danger')
    else:
        flash('Course updated successfully.', 'success')
    return redirect(url_for('admin.courses'))

@admin_bp.route('/courses/<int:course_id>/delete', methods=['POST'])
def delete_course(course_id):
    ok, msg = delete_or_archive_course(course_id, session['user_id'])
    flash(msg, 'info' if ok else 'danger')
    return redirect(url_for('admin.courses'))

# ----------------- EXAMINATIONS -----------------
@admin_bp.route('/examinations', methods=['GET', 'POST'])
def examinations():
    if request.method == 'POST':
        course_id = request.form.get('course_id')
        title = request.form.get('title')
        exam_type = request.form.get('exam_type')
        duration = request.form.get('duration_minutes')
        max_marks = request.form.get('max_marks')
        slot_start = request.form.get('slot_creation_start')
        slot_end = request.form.get('slot_creation_end')
        book_start = request.form.get('booking_start')
        book_end = request.form.get('booking_end')
        status = request.form.get('status', 'draft')

        if not (course_id and title and exam_type and duration and max_marks and slot_start and slot_end and book_start and book_end):
            flash('All examination fields are required.', 'warning')
        else:
            exam_id, err = create_examination(
                course_id, title, exam_type, int(duration), float(max_marks),
                slot_start, slot_end, book_start, book_end, status, session['user_id']
            )
            if err:
                flash(err, 'danger')
            else:
                flash(f'Examination "{title}" created successfully.', 'success')
                return redirect(url_for('admin.exam_detail', exam_id=exam_id))

    status_filter = request.args.get('status')
    search = request.args.get('search')
    exam_list = get_examinations(status=status_filter, search=search)
    course_list = get_courses(active_only=True)
    return render_template('admin/exams.html', exams=exam_list, courses=course_list, status_filter=status_filter, search=search)

@admin_bp.route('/examinations/<int:exam_id>')
def exam_detail(exam_id):
    exam = get_examination_by_id(exam_id)
    if not exam:
        flash('Examination not found.', 'danger')
        return redirect(url_for('admin.examinations'))

    rubrics = get_rubrics_by_exam(exam_id)
    total_weight = get_total_weightage(exam_id)
    assigned_examiners = get_assigned_examiners(exam_id)
    all_approved_examiners = list_examiners(approval_status='approved')
    slots = get_slots(examination_id=exam_id)
    evaluations = get_all_evaluations_for_exam(exam_id)

    return render_template(
        'admin/exam_detail.html',
        exam=exam,
        rubrics=rubrics,
        total_weight=total_weight,
        assigned_examiners=assigned_examiners,
        all_examiners=all_approved_examiners,
        slots=slots,
        evaluations=evaluations
    )

@admin_bp.route('/examinations/<int:exam_id>/edit', methods=['POST'])
def edit_exam(exam_id):
    title = request.form.get('title')
    exam_type = request.form.get('exam_type')
    duration = request.form.get('duration_minutes')
    max_marks = request.form.get('max_marks')
    slot_start = request.form.get('slot_creation_start')
    slot_end = request.form.get('slot_creation_end')
    book_start = request.form.get('booking_start')
    book_end = request.form.get('booking_end')
    status = request.form.get('status')

    ok, err = update_examination(
        exam_id, title, exam_type, int(duration), float(max_marks),
        slot_start, slot_end, book_start, book_end, status, session['user_id']
    )
    if err:
        flash(err, 'danger')
    else:
        flash('Examination updated successfully.', 'success')
    return redirect(url_for('admin.exam_detail', exam_id=exam_id))

@admin_bp.route('/examinations/<int:exam_id>/status', methods=['POST'])
def change_exam_status(exam_id):
    new_status = request.form.get('status')
    ok, err = update_exam_status(exam_id, new_status, session['user_id'])
    if err:
        flash(err, 'danger')
    else:
        flash(f'Examination status changed to "{new_status}".', 'success')
    return redirect(url_for('admin.exam_detail', exam_id=exam_id))

@admin_bp.route('/examinations/<int:exam_id>/assign-examiner', methods=['POST'])
def assign_examiner(exam_id):
    examiner_id = request.form.get('examiner_id')
    ok, err = assign_examiner_to_exam(exam_id, examiner_id, session['user_id'])
    if err:
        flash(err, 'danger')
    else:
        flash('Examiner assigned successfully.', 'success')
    return redirect(url_for('admin.exam_detail', exam_id=exam_id))

@admin_bp.route('/examinations/<int:exam_id>/unassign-examiner', methods=['POST'])
def unassign_examiner(exam_id):
    examiner_id = request.form.get('examiner_id')
    ok, err = unassign_examiner_from_exam(exam_id, examiner_id, session['user_id'])
    if err:
        flash(err, 'danger')
    else:
        flash('Examiner unassigned from examination.', 'info')
    return redirect(url_for('admin.exam_detail', exam_id=exam_id))

# ----------------- RUBRICS -----------------
@admin_bp.route('/examinations/<int:exam_id>/rubrics/add', methods=['POST'])
def add_rubric(exam_id):
    name = request.form.get('criterion_name')
    desc = request.form.get('description')
    max_m = request.form.get('max_marks')
    weight = request.form.get('weightage')
    order = request.form.get('display_order', 0)

    rid, err = add_rubric_criterion(exam_id, name, desc, max_m, weight, int(order or 0), session['user_id'])
    if err:
        flash(err, 'danger')
    else:
        flash('Rubric criterion added successfully.', 'success')
    return redirect(url_for('admin.exam_detail', exam_id=exam_id))

@admin_bp.route('/rubrics/<int:rubric_id>/edit', methods=['POST'])
def edit_rubric(rubric_id):
    exam_id = request.form.get('examination_id')
    name = request.form.get('criterion_name')
    desc = request.form.get('description')
    max_m = request.form.get('max_marks')
    weight = request.form.get('weightage')
    order = request.form.get('display_order', 0)

    ok, err = update_rubric_criterion(rubric_id, name, desc, max_m, weight, int(order or 0), session['user_id'])
    if err:
        flash(err, 'danger')
    else:
        flash('Rubric criterion updated successfully.', 'success')
    return redirect(url_for('admin.exam_detail', exam_id=exam_id))

@admin_bp.route('/rubrics/<int:rubric_id>/delete', methods=['POST'])
def delete_rubric(rubric_id):
    exam_id = request.form.get('examination_id')
    ok, err = delete_rubric_criterion(rubric_id, session['user_id'])
    if err:
        flash(err, 'danger')
    else:
        flash('Rubric criterion removed.', 'info')
    return redirect(url_for('admin.exam_detail', exam_id=exam_id))

# ----------------- EXAMINERS -----------------
@admin_bp.route('/examiners')
def examiners():
    status = request.args.get('status')
    search = request.args.get('search')
    examiner_list = list_examiners(approval_status=status, search=search)
    return render_template('admin/examiners.html', examiners=examiner_list, status=status, search=search)

@admin_bp.route('/examiners/<int:user_id>/status', methods=['POST'])
def change_examiner_status(user_id):
    new_status = request.form.get('status')
    ok, err = update_examiner_status(user_id, new_status, session['user_id'])
    if err:
        flash(err, 'danger')
    else:
        flash(f'Examiner approval status updated to {new_status}.', 'success')
    return redirect(url_for('admin.examiners'))

@admin_bp.route('/users/<int:user_id>/toggle-active', methods=['POST'])
def toggle_user_active(user_id):
    is_active = request.form.get('is_active') == '1'
    redirect_target = request.form.get('redirect_target', 'admin.examiners')
    ok, err = toggle_user_active_state(user_id, is_active, session['user_id'])
    if err:
        flash(err, 'danger')
    else:
        flash(f'User account {"activated" if is_active else "deactivated"}.', 'info')
    return redirect(url_for(redirect_target))

# ----------------- STUDENTS -----------------
@admin_bp.route('/students')
def students():
    search = request.args.get('search')
    student_list = list_students(search=search)
    return render_template('admin/students.html', students=student_list, search=search)

# ----------------- SLOTS & REASSIGNMENT -----------------
@admin_bp.route('/slots')
def slots():
    exam_id = request.args.get('examination_id')
    examiner_id = request.args.get('examiner_id')
    slot_list = get_slots(examination_id=exam_id, examiner_id=examiner_id)
    exams = get_examinations()
    examiners_list = list_examiners(approval_status='approved')
    return render_template('admin/slots.html', slots=slot_list, exams=exams, examiners=examiners_list, selected_exam=exam_id)

@admin_bp.route('/slots/<int:slot_id>/reassign', methods=['POST'])
def reassign_slot(slot_id):
    new_examiner_id = request.form.get('new_examiner_id')
    ok, err = reassign_slot_examiner(slot_id, new_examiner_id, session['user_id'])
    if err:
        flash(err, 'danger')
    else:
        flash('Slot examiner reassigned successfully while preserving booking history.', 'success')
    return redirect(url_for('admin.slots'))

# ----------------- BOOKINGS & RESCHEDULING -----------------
@admin_bp.route('/bookings')
def bookings():
    exam_id = request.args.get('examination_id')
    status = request.args.get('status')
    search = request.args.get('search')
    booking_list = get_all_bookings(examination_id=exam_id, status=status, search=search)
    exams = get_examinations()
    all_slots = get_slots()
    return render_template('admin/bookings.html', bookings=booking_list, exams=exams, all_slots=all_slots, selected_exam=exam_id, selected_status=status, search=search)

@admin_bp.route('/bookings/<int:booking_id>/reschedule', methods=['POST'])
def reschedule_booking(booking_id):
    new_slot_id = request.form.get('new_slot_id')
    reason = request.form.get('reason', 'Administrative rescheduling')
    ok, err = admin_reschedule_booking(booking_id, new_slot_id, session['user_id'], reason)
    if err:
        flash(err, 'danger')
    else:
        flash('Student booking rescheduled successfully.', 'success')
    return redirect(url_for('admin.bookings'))

# ----------------- RESULTS PUBLICATION -----------------
@admin_bp.route('/evaluations')
def evaluations():
    exams = get_examinations()
    return render_template('admin/evaluations.html', exams=exams)

@admin_bp.route('/examinations/<int:exam_id>/publish-results', methods=['POST'])
def publish_results(exam_id):
    notes = request.form.get('notes', 'Official Results Published')
    ok, err = publish_exam_results(exam_id, session['user_id'], notes)
    if err:
        flash(err, 'danger')
    else:
        flash('Results published! Students can now view their marks and feedback.', 'success')
    return redirect(url_for('admin.evaluations'))

@admin_bp.route('/examinations/<int:exam_id>/unpublish-results', methods=['POST'])
def unpublish_results(exam_id):
    ok, err = unpublish_exam_results(exam_id, session['user_id'])
    if err:
        flash(err, 'danger')
    else:
        flash('Results unpublished. Results are now hidden from students.', 'info')
    return redirect(url_for('admin.evaluations'))

# ----------------- AUDIT LOGS -----------------
@admin_bp.route('/audit-logs')
def audit_logs():
    action = request.args.get('action')
    entity = request.args.get('entity_type')
    search = request.args.get('search')
    logs = get_audit_logs(limit=200, entity_type=entity, action=action, search=search)
    return render_template('admin/audit_logs.html', logs=logs, action_filter=action, entity_filter=entity, search=search)
