from app.database import get_db
from app.services.exam_service import get_examination_by_id, is_slot_creation_allowed
from app.services.audit_service import log_audit

def get_slots(examination_id=None, examiner_id=None, status=None, date_from=None):
    db = get_db()
    query = """
        SELECT s.*, 
               e.title AS exam_title, e.max_marks, e.duration_minutes, e.status AS exam_status,
               c.code AS course_code, c.name AS course_name,
               u.username AS examiner_username, ep.full_name AS examiner_name
        FROM examination_slots s
        JOIN examinations e ON s.examination_id = e.id
        JOIN courses c ON e.course_id = c.id
        JOIN users u ON s.examiner_id = u.id
        JOIN examiner_profiles ep ON u.id = ep.user_id
        WHERE 1=1
    """
    params = []
    if examination_id:
        query += " AND s.examination_id = ?"
        params.append(examination_id)
    if examiner_id:
        query += " AND s.examiner_id = ?"
        params.append(examiner_id)
    if status:
        query += " AND s.status = ?"
        params.append(status)
    if date_from:
        query += " AND s.slot_date >= ?"
        params.append(date_from)

    query += " ORDER BY s.slot_date ASC, s.start_time ASC"
    return db.execute(query, params).fetchall()

def get_slot_by_id(slot_id):
    db = get_db()
    return db.execute(
        """
        SELECT s.*, 
               e.title AS exam_title, e.max_marks, e.duration_minutes, e.status AS exam_status,
               e.booking_start, e.booking_end,
               c.code AS course_code, c.name AS course_name,
               u.username AS examiner_username, ep.full_name AS examiner_name
        FROM examination_slots s
        JOIN examinations e ON s.examination_id = e.id
        JOIN courses c ON e.course_id = c.id
        JOIN users u ON s.examiner_id = u.id
        JOIN examiner_profiles ep ON u.id = ep.user_id
        WHERE s.id = ?
        """,
        (slot_id,)
    ).fetchone()

def check_examiner_slot_overlap(examiner_id, slot_date, start_time, end_time, exclude_slot_id=None):
    """
    Checks if the examiner already has an overlapping active slot on that date.
    Returns True if overlap exists, False otherwise.
    Overlap condition: (start_time < existing_end) AND (end_time > existing_start)
    """
    db = get_db()
    query = """
        SELECT id, start_time, end_time FROM examination_slots
        WHERE examiner_id = ? 
          AND slot_date = ? 
          AND status != 'cancelled'
          AND NOT (end_time <= ? OR start_time >= ?)
    """
    params = [examiner_id, slot_date, start_time, end_time]
    if exclude_slot_id:
        query += " AND id != ?"
        params.append(exclude_slot_id)

    overlapping = db.execute(query, params).fetchall()
    return len(overlapping) > 0

def create_slot(examination_id, examiner_id, slot_date, start_time, end_time, venue_or_link, capacity, bypass_window_check=False):
    db = get_db()
    exam = get_examination_by_id(examination_id)
    if not exam:
        return None, "Examination not found."

    # Verify examiner assignment to exam
    assignment = db.execute(
        """
        SELECT id FROM examiner_assignments 
        WHERE examination_id = ? AND examiner_id = ? AND is_active = 1
        """,
        (examination_id, examiner_id)
    ).fetchone()
    if not assignment:
        return None, "Examiner is not assigned to this examination."

    # Verify slot creation period
    if not bypass_window_check:
        allowed, reason = is_slot_creation_allowed(exam)
        if not allowed:
            return None, reason

    # Validate times
    if start_time >= end_time:
        return None, "Slot end time must be later than start time."

    capacity = int(capacity)
    if capacity <= 0:
        return None, "Slot capacity must be greater than zero."

    # Validate no overlapping slot for this examiner
    if check_examiner_slot_overlap(examiner_id, slot_date, start_time, end_time):
        return None, "This slot overlaps with an existing slot for the same examiner on this date."

    try:
        cursor = db.cursor()
        cursor.execute(
            """
            INSERT INTO examination_slots (
                examination_id, examiner_id, slot_date, start_time, end_time,
                venue_or_link, capacity, booked_count, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 0, 'available')
            """,
            (examination_id, examiner_id, slot_date, start_time, end_time, venue_or_link.strip(), capacity)
        )
        slot_id = cursor.lastrowid
        db.commit()

        log_audit(
            action="SLOT_CREATED",
            entity_type="examination_slots",
            entity_id=slot_id,
            details=f"Slot created for Exam {examination_id} on {slot_date} {start_time}-{end_time} (capacity {capacity})",
            user_id=examiner_id
        )
        return slot_id, None
    except Exception as e:
        db.rollback()
        return None, str(e)

def update_slot(slot_id, examiner_id, slot_date, start_time, end_time, venue_or_link, capacity, is_admin=False):
    db = get_db()
    slot = get_slot_by_id(slot_id)
    if not slot:
        return False, "Slot not found."

    if not is_admin and slot['examiner_id'] != examiner_id:
        return False, "You can only edit your own slots."

    # If students already booked, slot cannot be modified by examiner
    if not is_admin and slot['booked_count'] > 0:
        return False, "Cannot modify slot details because students have already booked this slot."

    if start_time >= end_time:
        return False, "Slot end time must be later than start time."

    capacity = int(capacity)
    if capacity < slot['booked_count']:
        return False, f"Capacity cannot be reduced below the current booked count ({slot['booked_count']})."

    # Check overlap
    if check_examiner_slot_overlap(slot['examiner_id'], slot_date, start_time, end_time, exclude_slot_id=slot_id):
        return False, "New time overlaps with another slot for this examiner."

    # Determine status
    new_status = 'full' if slot['booked_count'] >= capacity else 'available'

    try:
        db.execute(
            """
            UPDATE examination_slots
            SET slot_date = ?, start_time = ?, end_time = ?, venue_or_link = ?, capacity = ?, status = ?
            WHERE id = ?
            """,
            (slot_date, start_time, end_time, venue_or_link.strip(), capacity, new_status, slot_id)
        )
        db.commit()

        log_audit(
            action="SLOT_UPDATED",
            entity_type="examination_slots",
            entity_id=slot_id,
            details=f"Slot {slot_id} updated",
            user_id=examiner_id
        )
        return True, None
    except Exception as e:
        db.rollback()
        return False, str(e)

def cancel_slot(slot_id, user_id, is_admin=False):
    db = get_db()
    slot = get_slot_by_id(slot_id)
    if not slot:
        return False, "Slot not found."

    if not is_admin and slot['examiner_id'] != user_id:
        return False, "You can only cancel your own slots."

    if not is_admin and slot['booked_count'] > 0:
        return False, "Cannot cancel slot because students are booked. Please request administrator rescheduling."

    try:
        db.execute("UPDATE examination_slots SET status = 'cancelled' WHERE id = ?", (slot_id,))
        db.commit()

        log_audit(
            action="SLOT_CANCELLED",
            entity_type="examination_slots",
            entity_id=slot_id,
            details=f"Slot {slot_id} cancelled by {'admin' if is_admin else 'examiner'}",
            user_id=user_id
        )
        return True, None
    except Exception as e:
        db.rollback()
        return False, str(e)

def reassign_slot_examiner(slot_id, new_examiner_id, admin_user_id):
    """
    Reassigns an examiner to a slot while preserving all bookings and historical logs.
    """
    db = get_db()
    slot = get_slot_by_id(slot_id)
    if not slot:
        return False, "Slot not found."

    # Verify new examiner is assigned to the exam
    assignment = db.execute(
        "SELECT id FROM examiner_assignments WHERE examination_id = ? AND examiner_id = ? AND is_active = 1",
        (slot['examination_id'], new_examiner_id)
    ).fetchone()
    if not assignment:
        return False, "New examiner must first be assigned to this examination."

    # Verify no overlap for new examiner
    if check_examiner_slot_overlap(new_examiner_id, slot['slot_date'], slot['start_time'], slot['end_time'], exclude_slot_id=slot_id):
        return False, "New examiner already has an overlapping slot at this time."

    try:
        old_examiner_id = slot['examiner_id']
        db.execute("UPDATE examination_slots SET examiner_id = ? WHERE id = ?", (new_examiner_id, slot_id))
        db.commit()

        log_audit(
            action="SLOT_EXAMINER_REASSIGNED",
            entity_type="examination_slots",
            entity_id=slot_id,
            details=f"Examiner changed from User {old_examiner_id} to User {new_examiner_id} on slot {slot_id}",
            user_id=admin_user_id
        )
        return True, None
    except Exception as e:
        db.rollback()
        return False, str(e)
