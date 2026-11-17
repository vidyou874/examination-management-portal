from app.database import get_db
from app.services.rubric_service import get_rubrics_by_exam, calculate_weighted_final_score
from app.services.audit_service import log_audit

def get_booking_for_evaluation(booking_id, examiner_id, is_admin=False):
    """
    Retrieves booking details ensuring the examiner owns the slot or is admin.
    """
    db = get_db()
    booking = db.execute(
        """
        SELECT b.id as booking_id, b.status as booking_status, b.examination_id, b.student_id, b.slot_id,
               e.title as exam_title, e.max_marks, e.duration_minutes, e.status as exam_status,
               s.slot_date, s.start_time, s.end_time, s.venue_or_link, s.examiner_id as slot_examiner_id,
               sp.student_id_number, sp.full_name as student_name, sp.department, sp.program,
               ev.id as evaluation_id, ev.status as evaluation_status, ev.total_score, ev.remarks as evaluation_remarks,
               ev.submitted_at
        FROM bookings b
        JOIN examinations e ON b.examination_id = e.id
        JOIN examination_slots s ON b.slot_id = s.id
        JOIN student_profiles sp ON b.student_id = sp.user_id
        LEFT JOIN evaluations ev ON b.id = ev.booking_id
        WHERE b.id = ?
        """,
        (booking_id,)
    ).fetchone()

    if not booking:
        return None, "Booking not found."

    if booking['booking_status'] != 'confirmed':
        return None, f"Cannot evaluate a booking with status '{booking['booking_status']}'."

    if not is_admin and booking['slot_examiner_id'] != examiner_id:
        return None, "Unauthorized: You can only evaluate students booked into your assigned slot."

    return booking, None

def get_evaluation_details(evaluation_id):
    db = get_db()
    return db.execute(
        """
        SELECT ed.*, r.criterion_name, r.description, r.max_marks, r.weightage
        FROM evaluation_details ed
        JOIN examination_rubrics r ON ed.rubric_id = r.id
        WHERE ed.evaluation_id = ?
        ORDER BY r.display_order ASC, r.id ASC
        """,
        (evaluation_id,)
    ).fetchall()

def save_or_submit_evaluation(booking_id, examiner_id, marks_data, criterion_remarks, overall_remarks, is_submit=False, is_admin=False):
    """
    Saves draft evaluation or finalizes submission.
    marks_data: dict of {rubric_id: float_marks}
    criterion_remarks: dict of {rubric_id: str_remarks}
    """
    db = get_db()
    booking, err = get_booking_for_evaluation(booking_id, examiner_id, is_admin=is_admin)
    if err:
        return None, err

    # Check if already submitted
    if booking['evaluation_status'] == 'submitted' and not is_admin:
        return None, "This evaluation has already been submitted and cannot be modified without administrative permission."

    exam_id = booking['examination_id']
    rubrics = get_rubrics_by_exam(exam_id)
    if not rubrics:
        return None, "No rubric criteria configured for this examination. Please contact the administrator."

    # Validate each rubric mark
    awarded_marks_map = {}
    for r in rubrics:
        rid = r['id']
        val = marks_data.get(str(rid), marks_data.get(rid))
        if val is None or str(val).strip() == '':
            return None, f"Marks missing for criterion: '{r['criterion_name']}'."
        try:
            score = float(val)
        except (ValueError, TypeError):
            return None, f"Invalid number format for criterion '{r['criterion_name']}'."

        if score < 0:
            return None, f"Marks for '{r['criterion_name']}' cannot be negative."
        if score > float(r['max_marks']):
            return None, f"Marks for '{r['criterion_name']}' ({score}) exceed criterion maximum ({r['max_marks']})."

        awarded_marks_map[rid] = score

    # Compute weighted final score using PRD formula
    final_score = calculate_weighted_final_score(rubrics, awarded_marks_map, booking['max_marks'])

    eval_status = 'submitted' if is_submit else 'draft'

    cursor = db.cursor()
    try:
        cursor.execute("BEGIN IMMEDIATE;")

        if booking['evaluation_id']:
            eval_id = booking['evaluation_id']
            # Update existing
            cursor.execute(
                """
                UPDATE evaluations
                SET examiner_id = ?, total_score = ?, remarks = ?, status = ?,
                    submitted_at = CASE WHEN ? = 'submitted' THEN CURRENT_TIMESTAMP ELSE submitted_at END,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (examiner_id, final_score, overall_remarks.strip() if overall_remarks else None, eval_status, eval_status, eval_id)
            )
            # Remove old details to re-insert fresh
            cursor.execute("DELETE FROM evaluation_details WHERE evaluation_id = ?", (eval_id,))
        else:
            # Insert new
            cursor.execute(
                """
                INSERT INTO evaluations (
                    booking_id, examination_id, student_id, examiner_id,
                    total_score, remarks, status, submitted_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, CASE WHEN ? = 'submitted' THEN CURRENT_TIMESTAMP ELSE NULL END)
                """,
                (
                    booking_id, exam_id, booking['student_id'], examiner_id,
                    final_score, overall_remarks.strip() if overall_remarks else None,
                    eval_status, eval_status
                )
            )
            eval_id = cursor.lastrowid

        # Insert details
        for r in rubrics:
            rid = r['id']
            score = awarded_marks_map[rid]
            c_remark = criterion_remarks.get(str(rid), criterion_remarks.get(rid, ''))
            cursor.execute(
                """
                INSERT INTO evaluation_details (evaluation_id, rubric_id, marks_awarded, criterion_remarks)
                VALUES (?, ?, ?, ?)
                """,
                (eval_id, rid, score, c_remark.strip() if c_remark else None)
            )

        cursor.execute("COMMIT;")

        log_audit(
            action=f"EVALUATION_{eval_status.upper()}",
            entity_type="evaluations",
            entity_id=eval_id,
            details=f"Evaluation {eval_status} for booking {booking_id} by User {examiner_id}. Final score: {final_score}/{booking['max_marks']}",
            user_id=examiner_id
        )
        return eval_id, None

    except Exception as e:
        try:
            cursor.execute("ROLLBACK;")
        except Exception:
            pass
        return None, f"Failed to save evaluation: {str(e)}"

def publish_exam_results(examination_id, admin_user_id, notes=None):
    """
    Publishes results for an examination so students can see their marks and feedback.
    """
    db = get_db()
    try:
        db.execute(
            """
            INSERT INTO result_publications (examination_id, is_published, published_at, published_by, notes)
            VALUES (?, 1, CURRENT_TIMESTAMP, ?, ?)
            ON CONFLICT(examination_id) DO UPDATE SET
                is_published = 1,
                published_at = CURRENT_TIMESTAMP,
                published_by = excluded.published_by,
                notes = excluded.notes
            """,
            (examination_id, admin_user_id, notes)
        )
        db.commit()

        log_audit(
            action="RESULTS_PUBLISHED",
            entity_type="result_publications",
            entity_id=examination_id,
            details=f"Results published for Examination {examination_id}",
            user_id=admin_user_id
        )
        return True, None
    except Exception as e:
        db.rollback()
        return False, str(e)

def unpublish_exam_results(examination_id, admin_user_id):
    """
    Unpublishes results (hides marks from students).
    """
    db = get_db()
    try:
        db.execute(
            "UPDATE result_publications SET is_published = 0 WHERE examination_id = ?",
            (examination_id,)
        )
        db.commit()

        log_audit(
            action="RESULTS_UNPUBLISHED",
            entity_type="result_publications",
            entity_id=examination_id,
            details=f"Results unpublished for Examination {examination_id}",
            user_id=admin_user_id
        )
        return True, None
    except Exception as e:
        db.rollback()
        return False, str(e)

def get_student_published_results(student_id):
    """
    Returns evaluations for a student ONLY IF the examination result has been published.
    """
    db = get_db()
    return db.execute(
        """
        SELECT ev.*, 
               e.id as exam_id, e.title as exam_title, e.exam_type, e.max_marks as exam_max_marks,
               c.code as course_code, c.name as course_name,
               s.slot_date, s.start_time, s.end_time,
               ep.full_name as examiner_name,
               rp.published_at, rp.notes as publication_notes
        FROM evaluations ev
        JOIN bookings b ON ev.booking_id = b.id
        JOIN examinations e ON ev.examination_id = e.id
        JOIN courses c ON e.course_id = c.id
        JOIN examination_slots s ON b.slot_id = s.id
        JOIN examiner_profiles ep ON ev.examiner_id = ep.user_id
        JOIN result_publications rp ON e.id = rp.examination_id
        WHERE ev.student_id = ? AND rp.is_published = 1 AND ev.status = 'submitted'
        ORDER BY rp.published_at DESC
        """,
        (student_id,)
    ).fetchall()

def get_single_student_result(evaluation_id, student_id):
    """
    Returns single result with rubric breakdown if published.
    """
    db = get_db()
    result = db.execute(
        """
        SELECT ev.*, 
               e.id as exam_id, e.title as exam_title, e.exam_type, e.max_marks as exam_max_marks,
               c.code as course_code, c.name as course_name,
               s.slot_date, s.start_time, s.end_time, s.venue_or_link,
               ep.full_name as examiner_name,
               rp.published_at, rp.notes as publication_notes
        FROM evaluations ev
        JOIN bookings b ON ev.booking_id = b.id
        JOIN examinations e ON ev.examination_id = e.id
        JOIN courses c ON e.course_id = c.id
        JOIN examination_slots s ON b.slot_id = s.id
        JOIN examiner_profiles ep ON ev.examiner_id = ep.user_id
        JOIN result_publications rp ON e.id = rp.examination_id
        WHERE ev.id = ? AND ev.student_id = ? AND rp.is_published = 1
        """,
        (evaluation_id, student_id)
    ).fetchone()

    if not result:
        return None, None

    details = get_evaluation_details(evaluation_id)
    return result, details

def get_all_evaluations_for_exam(examination_id):
    db = get_db()
    return db.execute(
        """
        SELECT ev.*, 
               sp.student_id_number, sp.full_name as student_name,
               ep.full_name as examiner_name,
               b.slot_id, s.slot_date
        FROM evaluations ev
        JOIN student_profiles sp ON ev.student_id = sp.user_id
        JOIN examiner_profiles ep ON ev.examiner_id = ep.user_id
        JOIN bookings b ON ev.booking_id = b.id
        JOIN examination_slots s ON b.slot_id = s.id
        WHERE ev.examination_id = ?
        ORDER BY sp.student_id_number ASC
        """,
        (examination_id,)
    ).fetchall()
