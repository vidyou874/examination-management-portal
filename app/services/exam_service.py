from datetime import datetime
from app.database import get_db
from app.services.audit_service import log_audit

VALID_EXAM_STATUSES = ('draft', 'slot_creation', 'booking_open', 'closed', 'completed')

def get_examinations(status=None, course_id=None, search=None):
    db = get_db()
    query = """
        SELECT e.*, c.code AS course_code, c.name AS course_name,
               (SELECT COUNT(*) FROM examination_slots s WHERE s.examination_id = e.id) AS slot_count,
               (SELECT COUNT(*) FROM bookings b WHERE b.examination_id = e.id AND b.status = 'confirmed') AS active_bookings_count,
               (SELECT COUNT(*) FROM examiner_assignments ea WHERE ea.examination_id = e.id AND ea.is_active = 1) AS assigned_examiners_count,
               (SELECT is_published FROM result_publications rp WHERE rp.examination_id = e.id) AS is_published
        FROM examinations e
        JOIN courses c ON e.course_id = c.id
        WHERE 1=1
    """
    params = []
    if status:
        query += " AND e.status = ?"
        params.append(status)
    if course_id:
        query += " AND e.course_id = ?"
        params.append(course_id)
    if search:
        query += " AND (e.title LIKE ? OR c.code LIKE ? OR c.name LIKE ?)"
        wildcard = f"%{search}%"
        params.extend([wildcard, wildcard, wildcard])

    query += " ORDER BY e.created_at DESC"
    return db.execute(query, params).fetchall()

def get_examination_by_id(exam_id):
    db = get_db()
    return db.execute(
        """
        SELECT e.*, c.code AS course_code, c.name AS course_name,
               (SELECT COUNT(*) FROM examination_slots s WHERE s.examination_id = e.id) AS slot_count,
               (SELECT COUNT(*) FROM bookings b WHERE b.examination_id = e.id AND b.status = 'confirmed') AS active_bookings_count,
               (SELECT is_published FROM result_publications rp WHERE rp.examination_id = e.id) AS is_published
        FROM examinations e
        JOIN courses c ON e.course_id = c.id
        WHERE e.id = ?
        """,
        (exam_id,)
    ).fetchone()

def create_examination(course_id, title, exam_type, duration_minutes, max_marks,
                       slot_creation_start, slot_creation_end,
                       booking_start, booking_end, status='draft', admin_user_id=None):
    db = get_db()
    if status not in VALID_EXAM_STATUSES:
        return None, f"Invalid examination status: {status}"

    try:
        cursor = db.cursor()
        cursor.execute(
            """
            INSERT INTO examinations (
                course_id, title, exam_type, duration_minutes, max_marks,
                slot_creation_start, slot_creation_end, booking_start, booking_end, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                course_id, title.strip(), exam_type.strip(), duration_minutes, max_marks,
                slot_creation_start, slot_creation_end, booking_start, booking_end, status
            )
        )
        exam_id = cursor.lastrowid

        # Initialize result_publications record
        cursor.execute(
            "INSERT INTO result_publications (examination_id, is_published) VALUES (?, 0)",
            (exam_id,)
        )
        db.commit()

        log_audit(
            action="EXAM_CREATED",
            entity_type="examinations",
            entity_id=exam_id,
            details=f"Examination created: {title} (Course ID {course_id})",
            user_id=admin_user_id
        )
        return exam_id, None
    except Exception as e:
        db.rollback()
        return None, str(e)

def update_examination(exam_id, title, exam_type, duration_minutes, max_marks,
                       slot_creation_start, slot_creation_end,
                       booking_start, booking_end, status, admin_user_id=None):
    db = get_db()
    if status not in VALID_EXAM_STATUSES:
        return False, f"Invalid examination status: {status}"

    try:
        db.execute(
            """
            UPDATE examinations
            SET title = ?, exam_type = ?, duration_minutes = ?, max_marks = ?,
                slot_creation_start = ?, slot_creation_end = ?,
                booking_start = ?, booking_end = ?, status = ?
            WHERE id = ?
            """,
            (
                title.strip(), exam_type.strip(), duration_minutes, max_marks,
                slot_creation_start, slot_creation_end, booking_start, booking_end, status,
                exam_id
            )
        )
        db.commit()

        log_audit(
            action="EXAM_UPDATED",
            entity_type="examinations",
            entity_id=exam_id,
            details=f"Examination updated: {title} (status={status})",
            user_id=admin_user_id
        )
        return True, None
    except Exception as e:
        db.rollback()
        return False, str(e)

def update_exam_status(exam_id, new_status, admin_user_id=None):
    if new_status not in VALID_EXAM_STATUSES:
        return False, f"Invalid examination status: {new_status}"

    db = get_db()
    try:
        db.execute("UPDATE examinations SET status = ? WHERE id = ?", (new_status, exam_id))
        db.commit()
        log_audit(
            action="EXAM_STATUS_CHANGED",
            entity_type="examinations",
            entity_id=exam_id,
            details=f"Examination status moved to {new_status}",
            user_id=admin_user_id
        )
        return True, None
    except Exception as e:
        db.rollback()
        return False, str(e)

def get_assigned_examiners(exam_id):
    db = get_db()
    return db.execute(
        """
        SELECT ea.id as assignment_id, ea.is_active, ea.assigned_at,
               u.id as examiner_id, u.username, u.email,
               ep.employee_id, ep.full_name, ep.department, ep.designation
        FROM examiner_assignments ea
        JOIN users u ON ea.examiner_id = u.id
        JOIN examiner_profiles ep ON u.id = ep.user_id
        WHERE ea.examination_id = ?
        ORDER BY ep.full_name ASC
        """,
        (exam_id,)
    ).fetchall()

def assign_examiner_to_exam(exam_id, examiner_id, admin_user_id=None):
    db = get_db()
    # Check if examiner is approved
    examiner = db.execute(
        """
        SELECT u.id, ep.approval_status 
        FROM users u 
        JOIN examiner_profiles ep ON u.id = ep.user_id 
        WHERE u.id = ? AND u.role = 'examiner'
        """,
        (examiner_id,)
    ).fetchone()
    if not examiner or examiner['approval_status'] != 'approved':
        return False, "Only approved examiners can be assigned to examinations."

    try:
        db.execute(
            """
            INSERT INTO examiner_assignments (examination_id, examiner_id, is_active)
            VALUES (?, ?, 1)
            ON CONFLICT(examination_id, examiner_id) DO UPDATE SET is_active = 1
            """,
            (exam_id, examiner_id)
        )
        db.commit()
        log_audit(
            action="EXAMINER_ASSIGNED",
            entity_type="examiner_assignments",
            entity_id=exam_id,
            details=f"Examiner {examiner_id} assigned to Exam {exam_id}",
            user_id=admin_user_id
        )
        return True, None
    except Exception as e:
        db.rollback()
        return False, str(e)

def unassign_examiner_from_exam(exam_id, examiner_id, admin_user_id=None):
    db = get_db()
    # Soft deactivate assignment rather than delete to preserve history
    try:
        db.execute(
            """
            UPDATE examiner_assignments 
            SET is_active = 0 
            WHERE examination_id = ? AND examiner_id = ?
            """,
            (exam_id, examiner_id)
        )
        db.commit()
        log_audit(
            action="EXAMINER_UNASSIGNED",
            entity_type="examiner_assignments",
            entity_id=exam_id,
            details=f"Examiner {examiner_id} assignment deactivated for Exam {exam_id}",
            user_id=admin_user_id
        )
        return True, None
    except Exception as e:
        db.rollback()
        return False, str(e)

def get_examiner_assigned_exams(examiner_id):
    db = get_db()
    return db.execute(
        """
        SELECT e.*, c.code AS course_code, c.name AS course_name,
               (SELECT COUNT(*) FROM examination_slots s 
                WHERE s.examination_id = e.id AND s.examiner_id = ?) AS my_slots_count
        FROM examinations e
        JOIN courses c ON e.course_id = c.id
        JOIN examiner_assignments ea ON e.id = ea.examination_id
        WHERE ea.examiner_id = ? AND ea.is_active = 1
        ORDER BY e.created_at DESC
        """,
        (examiner_id, examiner_id)
    ).fetchall()

def is_slot_creation_allowed(exam):
    """
    Checks if slot creation is permitted by exam status and timeline.
    Admin can also explicitly open it via status 'slot_creation'.
    """
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    start_str = str(exam['slot_creation_start']).replace('T', ' ')
    end_str = str(exam['slot_creation_end']).replace('T', ' ')

    if exam['status'] == 'slot_creation':
        return True, None
    
    # Also valid if within dates and status allows
    if exam['status'] in ('draft', 'slot_creation', 'booking_open'):
        if start_str <= now <= end_str:
            return True, None
        elif now < start_str:
            return False, f"Slot creation has not started yet (Opens on {exam['slot_creation_start']})."
        else:
            return False, f"Slot creation deadline passed on {exam['slot_creation_end']}."
    
    return False, f"Exam status is '{exam['status']}', slot creation is not open."

def is_student_booking_allowed(exam):
    """
    Checks if student booking is currently open based on lifecycle status and deadlines.
    """
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    start_str = str(exam['booking_start']).replace('T', ' ')
    end_str = str(exam['booking_end']).replace('T', ' ')

    if exam['status'] == 'completed':
        return False, "This examination has already been conducted and concluded."

    if exam['status'] == 'closed':
        return False, "Examination booking has been closed by administration."

    if exam['status'] == 'draft':
        return False, "This examination is still in planning (Draft phase)."

    if exam['status'] == 'slot_creation':
        return False, f"Faculty slot creation is in progress. Student booking opens on {exam['booking_start']}."

    if exam['status'] == 'booking_open':
        if now < start_str:
            return False, f"Student booking has not opened yet (Opens on {exam['booking_start']})."
        if now > end_str:
            return False, f"Booking deadline passed on {exam['booking_end']}."
        return True, None

    return False, f"Exam status is '{exam['status']}'. Bookings are closed."
