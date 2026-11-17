from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from app.decorators import role_required
from app.database import get_db
from app.services.auth_service import get_student_profile
from app.services.exam_service import get_examinations, get_examination_by_id, is_student_booking_allowed
from app.services.slot_service import get_slots
from app.services.booking_service import book_examination_slot, cancel_booking, get_student_bookings, get_booking_events
from app.services.evaluation_service import get_student_published_results, get_single_student_result

student_bp = Blueprint('student', __name__, url_prefix='/student')

@student_bp.before_request
@role_required('student')
def check_student():
    pass

@student_bp.route('/dashboard')
def dashboard():
    student_id = session['user_id']
    profile = get_student_profile(student_id)
    bookings = get_student_bookings(student_id)
    published_results = get_student_published_results(student_id)

    # Active upcoming bookings
    active_bookings = [b for b in bookings if b['status'] == 'confirmed']
    past_bookings = [b for b in bookings if b['status'] != 'confirmed']

    # Open examinations available for booking
    all_exams = get_examinations()
    available_to_book = []
    booked_exam_ids = {b['exam_id'] for b in active_bookings}

    for e in all_exams:
        is_open, _ = is_student_booking_allowed(e)
        if is_open and e['id'] not in booked_exam_ids:
            available_to_book.append(e)

    return render_template(
        'student/dashboard.html',
        profile=profile,
        active_bookings=active_bookings,
        available_exams=available_to_book[:5],
        recent_results=published_results[:5],
        stats={
            'active_bookings_count': len(active_bookings),
            'published_results_count': len(published_results),
            'available_exams_count': len(available_to_book)
        }
    )

@student_bp.route('/examinations')
def examinations():
    student_id = session['user_id']
    search = request.args.get('search')
    course_id = request.args.get('course_id')

    exams = get_examinations(course_id=course_id, search=search)
    active_bookings = get_student_bookings(student_id)
    booked_exam_ids = {b['exam_id'] for b in active_bookings if b['status'] == 'confirmed'}

    # Fetch courses for dropdown filter
    db = get_db()
    courses = db.execute("SELECT * FROM courses WHERE is_active = 1 ORDER BY code ASC").fetchall()

    return render_template(
        'student/exams.html',
        exams=exams,
        courses=courses,
        booked_exam_ids=booked_exam_ids,
        search=search,
        selected_course=course_id
    )

@student_bp.route('/examinations/<int:exam_id>/slots')
def exam_slots(exam_id):
    student_id = session['user_id']
    exam = get_examination_by_id(exam_id)
    if not exam:
        flash('Examination not found.', 'danger')
        return redirect(url_for('student.examinations'))

    allowed, booking_msg = is_student_booking_allowed(exam)

    # Check if student already holds active booking
    db = get_db()
    my_booking = db.execute(
        "SELECT * FROM bookings WHERE examination_id = ? AND student_id = ? AND status = 'confirmed'",
        (exam_id, student_id)
    ).fetchone()

    slots = get_slots(examination_id=exam_id)
    return render_template(
        'student/exam_slots.html',
        exam=exam,
        slots=slots,
        is_booking_open=allowed,
        booking_msg=booking_msg,
        my_booking=my_booking
    )

@student_bp.route('/examinations/<int:exam_id>/book', methods=['POST'])
def book_slot_route(exam_id):
    student_id = session['user_id']
    slot_id = request.form.get('slot_id')

    if not slot_id:
        flash('Please select a slot to book.', 'warning')
        return redirect(url_for('student.exam_slots', exam_id=exam_id))

    booking_id, err = book_examination_slot(student_id, exam_id, int(slot_id))
    if err:
        flash(err, 'danger')
        return redirect(url_for('student.exam_slots', exam_id=exam_id))

    flash('Slot booked successfully! Your examination reservation is confirmed.', 'success')
    return redirect(url_for('student.my_bookings'))

@student_bp.route('/bookings')
def my_bookings():
    student_id = session['user_id']
    bookings = get_student_bookings(student_id)
    return render_template('student/my_bookings.html', bookings=bookings)

@student_bp.route('/bookings/<int:booking_id>/cancel', methods=['POST'])
def cancel_booking_route(booking_id):
    student_id = session['user_id']
    reason = request.form.get('reason', 'Cancelled by student')

    ok, err = cancel_booking(booking_id, student_id, reason=reason)
    if err:
        flash(err, 'danger')
    else:
        flash('Booking cancelled successfully. The slot capacity has been restored for other students.', 'info')
    return redirect(url_for('student.my_bookings'))

@student_bp.route('/bookings/<int:booking_id>/events')
def booking_history(booking_id):
    student_id = session['user_id']
    db = get_db()
    booking = db.execute(
        "SELECT * FROM bookings WHERE id = ? AND student_id = ?",
        (booking_id, student_id)
    ).fetchone()
    if not booking:
        flash('Booking not found.', 'danger')
        return redirect(url_for('student.my_bookings'))

    events = get_booking_events(booking_id)
    return render_template('student/booking_events.html', booking=booking, events=events)

@student_bp.route('/results')
def results():
    student_id = session['user_id']
    published_results = get_student_published_results(student_id)
    return render_template('student/results.html', results=published_results)

@student_bp.route('/results/<int:evaluation_id>')
def result_detail(evaluation_id):
    student_id = session['user_id']
    result, details = get_single_student_result(evaluation_id, student_id)
    if not result:
        flash('Result not available or not yet published.', 'warning')
        return redirect(url_for('student.results'))

    return render_template('student/result_detail.html', result=result, details=details)

@student_bp.route('/profile', methods=['GET', 'POST'])
def profile():
    student_id = session['user_id']
    db = get_db()

    if request.method == 'POST':
        full_name = request.form.get('full_name')
        department = request.form.get('department')
        program = request.form.get('program')
        phone = request.form.get('phone')

        if full_name and department and program:
            db.execute(
                """
                UPDATE student_profiles
                SET full_name = ?, department = ?, program = ?, phone = ?
                WHERE user_id = ?
                """,
                (full_name.strip(), department.strip(), program.strip(), phone, student_id)
            )
            db.commit()
            flash('Profile updated successfully.', 'success')
        else:
            flash('Please complete all required profile fields.', 'warning')

    student_data = get_student_profile(student_id)
    return render_template('student/profile.html', student=student_data)
