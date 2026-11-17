from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from app.decorators import role_required
from app.database import get_db
from app.services.exam_service import get_examiner_assigned_exams, get_examination_by_id, is_slot_creation_allowed
from app.services.slot_service import get_slots, get_slot_by_id, create_slot, update_slot, cancel_slot
from app.services.booking_service import get_slot_roster
from app.services.rubric_service import get_rubrics_by_exam
from app.services.evaluation_service import get_booking_for_evaluation, get_evaluation_details, save_or_submit_evaluation

examiner_bp = Blueprint('examiner', __name__, url_prefix='/examiner')

@examiner_bp.before_request
@role_required('examiner')
def check_examiner():
    pass

@examiner_bp.route('/dashboard')
def dashboard():
    examiner_id = session['user_id']
    db = get_db()

    assigned_exams = get_examiner_assigned_exams(examiner_id)
    my_slots = get_slots(examiner_id=examiner_id)
    
    # Calculate stats
    total_slots = len(my_slots)
    total_booked_students = sum(s['booked_count'] for s in my_slots)
    
    # Pending evaluations: confirmed bookings in examiner's slots that are either not evaluated or in 'draft'
    pending_evals = db.execute(
        """
        SELECT COUNT(b.id)
        FROM bookings b
        JOIN examination_slots s ON b.slot_id = s.id
        LEFT JOIN evaluations ev ON b.id = ev.booking_id
        WHERE s.examiner_id = ? AND b.status = 'confirmed' 
          AND (ev.id IS NULL OR ev.status = 'draft')
        """,
        (examiner_id,)
    ).fetchone()[0]

    submitted_evals = db.execute(
        """
        SELECT COUNT(id) FROM evaluations
        WHERE examiner_id = ? AND status = 'submitted'
        """,
        (examiner_id,)
    ).fetchone()[0]

    return render_template(
        'examiner/dashboard.html',
        assigned_exams=assigned_exams,
        slots=my_slots[:5],
        stats={
            'assigned_exams_count': len(assigned_exams),
            'total_slots': total_slots,
            'booked_students': total_booked_students,
            'pending_evaluations': pending_evals,
            'submitted_evaluations': submitted_evals
        }
    )

@examiner_bp.route('/examinations')
def examinations():
    examiner_id = session['user_id']
    assigned_exams = get_examiner_assigned_exams(examiner_id)
    return render_template('examiner/exams.html', exams=assigned_exams)

@examiner_bp.route('/slots')
def slots():
    examiner_id = session['user_id']
    exam_id = request.args.get('examination_id')
    my_slots = get_slots(examiner_id=examiner_id, examination_id=exam_id)
    assigned_exams = get_examiner_assigned_exams(examiner_id)
    return render_template('examiner/slots.html', slots=my_slots, exams=assigned_exams, selected_exam=exam_id)

@examiner_bp.route('/slots/create', methods=['GET', 'POST'])
def create_slot_route():
    examiner_id = session['user_id']
    assigned_exams = get_examiner_assigned_exams(examiner_id)

    if request.method == 'POST':
        exam_id = request.form.get('examination_id')
        slot_date = request.form.get('slot_date')
        start_time = request.form.get('start_time')
        end_time = request.form.get('end_time')
        venue = request.form.get('venue_or_link')
        capacity = request.form.get('capacity')

        if not (exam_id and slot_date and start_time and end_time and venue and capacity):
            flash('All slot fields are required.', 'warning')
        else:
            slot_id, err = create_slot(
                int(exam_id), examiner_id, slot_date, start_time, end_time, venue, int(capacity)
            )
            if err:
                flash(err, 'danger')
            else:
                flash('Examination slot created successfully.', 'success')
                return redirect(url_for('examiner.slots'))

    preselect_exam = request.args.get('examination_id')
    return render_template('examiner/create_slot.html', exams=assigned_exams, selected_exam=preselect_exam)

@examiner_bp.route('/slots/<int:slot_id>/edit', methods=['POST'])
def edit_slot(slot_id):
    examiner_id = session['user_id']
    slot_date = request.form.get('slot_date')
    start_time = request.form.get('start_time')
    end_time = request.form.get('end_time')
    venue = request.form.get('venue_or_link')
    capacity = request.form.get('capacity')

    ok, err = update_slot(slot_id, examiner_id, slot_date, start_time, end_time, venue, capacity)
    if err:
        flash(err, 'danger')
    else:
        flash('Slot updated successfully.', 'success')
    return redirect(url_for('examiner.slots'))

@examiner_bp.route('/slots/<int:slot_id>/cancel', methods=['POST'])
def cancel_slot_route(slot_id):
    examiner_id = session['user_id']
    ok, err = cancel_slot(slot_id, examiner_id)
    if err:
        flash(err, 'danger')
    else:
        flash('Slot cancelled successfully.', 'info')
    return redirect(url_for('examiner.slots'))

@examiner_bp.route('/slots/<int:slot_id>/roster')
def slot_roster(slot_id):
    examiner_id = session['user_id']
    slot = get_slot_by_id(slot_id)
    if not slot or slot['examiner_id'] != examiner_id:
        flash('Slot not found or unauthorized.', 'danger')
        return redirect(url_for('examiner.slots'))

    students = get_slot_roster(slot_id)
    return render_template('examiner/slot_roster.html', slot=slot, students=students)

@examiner_bp.route('/evaluate/<int:booking_id>', methods=['GET', 'POST'])
def evaluate_student(booking_id):
    examiner_id = session['user_id']
    booking, err = get_booking_for_evaluation(booking_id, examiner_id)
    if err:
        flash(err, 'danger')
        return redirect(url_for('examiner.slots'))

    rubrics = get_rubrics_by_exam(booking['examination_id'])
    if not rubrics:
        flash('Cannot evaluate: No rubric criteria have been set for this examination.', 'warning')
        return redirect(url_for('examiner.slot_roster', slot_id=booking['slot_id']))

    # Load existing details if any
    existing_details = {}
    if booking['evaluation_id']:
        details_rows = get_evaluation_details(booking['evaluation_id'])
        for row in details_rows:
            existing_details[row['rubric_id']] = {
                'marks': row['marks_awarded'],
                'remarks': row['criterion_remarks'] or ''
            }

    if request.method == 'POST':
        action_type = request.form.get('action_type', 'save_draft')
        is_submit = (action_type == 'submit_final')

        marks_data = {}
        criterion_remarks = {}
        for r in rubrics:
            rid = str(r['id'])
            marks_data[rid] = request.form.get(f'marks_{rid}')
            criterion_remarks[rid] = request.form.get(f'remarks_{rid}', '')

        overall_remarks = request.form.get('overall_remarks', '')

        eval_id, save_err = save_or_submit_evaluation(
            booking_id, examiner_id, marks_data, criterion_remarks, overall_remarks, is_submit=is_submit
        )
        if save_err:
            flash(save_err, 'danger')
        else:
            if is_submit:
                flash(f'Evaluation for {booking["student_name"]} submitted successfully! Marks are finalized.', 'success')
            else:
                flash('Draft evaluation saved successfully. You can return to edit and submit later.', 'info')
            return redirect(url_for('examiner.slot_roster', slot_id=booking['slot_id']))

    return render_template(
        'examiner/evaluate.html',
        booking=booking,
        rubrics=rubrics,
        existing_details=existing_details
    )

@examiner_bp.route('/evaluations/history')
def evaluations_history():
    examiner_id = session['user_id']
    db = get_db()
    evaluations = db.execute(
        """
        SELECT ev.*, 
               e.title as exam_title, e.max_marks as exam_max_marks,
               sp.student_id_number, sp.full_name as student_name,
               s.slot_date, s.start_time, s.end_time
        FROM evaluations ev
        JOIN examinations e ON ev.examination_id = e.id
        JOIN student_profiles sp ON ev.student_id = sp.user_id
        JOIN bookings b ON ev.booking_id = b.id
        JOIN examination_slots s ON b.slot_id = s.id
        WHERE ev.examiner_id = ?
        ORDER BY ev.updated_at DESC
        """,
        (examiner_id,)
    ).fetchall()
    return render_template('examiner/history.html', evaluations=evaluations)
