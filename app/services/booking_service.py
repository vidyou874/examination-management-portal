from datetime import datetime
from app.database import get_db
from app.services.exam_service import get_examination_by_id, is_student_booking_allowed
from app.services.audit_service import log_audit

def book_examination_slot(student_id, examination_id, slot_id, reason="Student self-booking", bypass_window_check=False):
    """
    Atomically books a slot for a student ensuring capacity and duplicate booking constraints.
    Returns (booking_id, error_message).
    """
    db = get_db()
    cursor = db.cursor()

    try:
        cursor.execute("BEGIN IMMEDIATE;")

        # 1. Check examination and booking window
        exam = cursor.execute("SELECT * FROM examinations WHERE id = ?", (examination_id,)).fetchone()
        if not exam:
            cursor.execute("ROLLBACK;")
            return None, "Examination not found."

        if not bypass_window_check:
            allowed, msg = is_student_booking_allowed(exam)
            if not allowed:
                cursor.execute("ROLLBACK;")
                return None, msg

        # 2. Check duplicate active booking for this exam
        existing_booking = cursor.execute(
            """
            SELECT id FROM bookings 
            WHERE examination_id = ? AND student_id = ? AND status = 'confirmed'
            """,
            (examination_id, student_id)
        ).fetchone()
        if existing_booking:
            cursor.execute("ROLLBACK;")
            return None, "You already have an active booking for this examination."

        # 3. Fetch and lock slot row
        slot = cursor.execute(
            """
            SELECT id, examination_id, capacity, booked_count, status 
            FROM examination_slots 
            WHERE id = ?
            """,
            (slot_id,)
        ).fetchone()

        if not slot:
            cursor.execute("ROLLBACK;")
            return None, "Selected slot does not exist."

        if slot['examination_id'] != examination_id:
            cursor.execute("ROLLBACK;")
            return None, "Slot does not belong to this examination."

        if slot['status'] == 'cancelled':
            cursor.execute("ROLLBACK;")
            return None, "This slot has been cancelled."

        # Strict capacity check
        if slot['booked_count'] >= slot['capacity'] or slot['status'] == 'full':
            cursor.execute("ROLLBACK;")
            return None, "This slot is already full. Please select another slot."

        # 4. Create booking
        cursor.execute(
            """
            INSERT INTO bookings (examination_id, slot_id, student_id, status)
            VALUES (?, ?, ?, 'confirmed')
            """,
            (examination_id, slot_id, student_id)
        )
        booking_id = cursor.lastrowid

        # 5. Update slot booked count and full status
        new_count = slot['booked_count'] + 1
        new_status = 'full' if new_count >= slot['capacity'] else 'available'
        cursor.execute(
            """
            UPDATE examination_slots
            SET booked_count = ?, status = ?
            WHERE id = ?
            """,
            (new_count, new_status, slot_id)
        )

        # 6. Record booking event
        cursor.execute(
            """
            INSERT INTO booking_events (booking_id, event_type, new_slot_id, triggered_by_user_id, reason)
            VALUES (?, 'booked', ?, ?, ?)
            """,
            (booking_id, slot_id, student_id, reason)
        )

        cursor.execute("COMMIT;")

        log_audit(
            action="SLOT_BOOKED",
            entity_type="bookings",
            entity_id=booking_id,
            details=f"Student {student_id} booked slot {slot_id} for exam {examination_id}",
            user_id=student_id
        )
        return booking_id, None

    except Exception as e:
        try:
            cursor.execute("ROLLBACK;")
        except Exception:
            pass
        return None, f"Booking transaction failed: {str(e)}"

def cancel_booking(booking_id, user_id, reason="Cancelled by student", is_admin=False):
    """
    Cancels an active booking, decrements slot booked_count, and restores 'available' status.
    """
    db = get_db()
    cursor = db.cursor()

    try:
        cursor.execute("BEGIN IMMEDIATE;")

        booking = cursor.execute(
            """
            SELECT b.*, e.booking_end, e.status as exam_status
            FROM bookings b
            JOIN examinations e ON b.examination_id = e.id
            WHERE b.id = ?
            """,
            (booking_id,)
        ).fetchone()

        if not booking:
            cursor.execute("ROLLBACK;")
            return False, "Booking not found."

        if not is_admin and booking['student_id'] != user_id:
            cursor.execute("ROLLBACK;")
            return False, "You are not authorized to cancel this booking."

        if booking['status'] != 'confirmed':
            cursor.execute("ROLLBACK;")
            return False, f"Booking is already {booking['status']}."

        # Check booking deadline if student is cancelling
        if not is_admin:
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            end_str = str(booking['booking_end']).replace('T', ' ')
            if now > end_str:
                cursor.execute("ROLLBACK;")
                return False, f"Cancellation deadline passed on {booking['booking_end']}."

        # Update booking
        cursor.execute(
            """
            UPDATE bookings
            SET status = 'cancelled', cancelled_at = CURRENT_TIMESTAMP, cancellation_reason = ?
            WHERE id = ?
            """,
            (reason, booking_id)
        )

        # Restore slot capacity
        slot = cursor.execute(
            "SELECT capacity, booked_count FROM examination_slots WHERE id = ?",
            (booking['slot_id'],)
        ).fetchone()

        if slot:
            new_count = max(0, slot['booked_count'] - 1)
            new_status = 'available' if new_count < slot['capacity'] else 'full'
            cursor.execute(
                """
                UPDATE examination_slots
                SET booked_count = ?, status = ?
                WHERE id = ?
                """,
                (new_count, new_status, booking['slot_id'])
            )

        # Record booking event
        cursor.execute(
            """
            INSERT INTO booking_events (booking_id, event_type, old_slot_id, triggered_by_user_id, reason)
            VALUES (?, 'cancelled', ?, ?, ?)
            """,
            (booking_id, booking['slot_id'], user_id, reason)
        )

        cursor.execute("COMMIT;")

        log_audit(
            action="BOOKING_CANCELLED",
            entity_type="bookings",
            entity_id=booking_id,
            details=f"Booking {booking_id} cancelled by User {user_id}. Reason: {reason}",
            user_id=user_id
        )
        return True, None

    except Exception as e:
        try:
            cursor.execute("ROLLBACK;")
        except Exception:
            pass
        return False, f"Cancellation failed: {str(e)}"

def admin_reschedule_booking(booking_id, new_slot_id, admin_user_id, reason="Administrative reschedule"):
    """
    Reschedules a booking to a new slot of the same exam, verifying capacity and preserving event history.
    """
    db = get_db()
    cursor = db.cursor()

    try:
        cursor.execute("BEGIN IMMEDIATE;")

        booking = cursor.execute(
            "SELECT * FROM bookings WHERE id = ?",
            (booking_id,)
        ).fetchone()

        if not booking:
            cursor.execute("ROLLBACK;")
            return False, "Booking not found."

        if booking['status'] != 'confirmed':
            cursor.execute("ROLLBACK;")
            return False, f"Cannot reschedule booking with status '{booking['status']}'."

        if booking['slot_id'] == new_slot_id:
            cursor.execute("ROLLBACK;")
            return False, "Booking is already in this slot."

        # Fetch and validate destination slot
        new_slot = cursor.execute(
            "SELECT * FROM examination_slots WHERE id = ?",
            (new_slot_id,)
        ).fetchone()

        if not new_slot:
            cursor.execute("ROLLBACK;")
            return False, "Destination slot does not exist."

        if new_slot['examination_id'] != booking['examination_id']:
            cursor.execute("ROLLBACK;")
            return False, "Destination slot must belong to the same examination."

        if new_slot['status'] == 'cancelled':
            cursor.execute("ROLLBACK;")
            return False, "Destination slot has been cancelled."

        if new_slot['booked_count'] >= new_slot['capacity']:
            cursor.execute("ROLLBACK;")
            return False, "Destination slot has reached full capacity."

        old_slot_id = booking['slot_id']

        # Decrement old slot count
        old_slot = cursor.execute(
            "SELECT capacity, booked_count FROM examination_slots WHERE id = ?",
            (old_slot_id,)
        ).fetchone()
        if old_slot:
            new_old_count = max(0, old_slot['booked_count'] - 1)
            cursor.execute(
                "UPDATE examination_slots SET booked_count = ?, status = 'available' WHERE id = ?",
                (new_old_count, old_slot_id)
            )

        # Increment new slot count
        new_slot_count = new_slot['booked_count'] + 1
        new_slot_status = 'full' if new_slot_count >= new_slot['capacity'] else 'available'
        cursor.execute(
            "UPDATE examination_slots SET booked_count = ?, status = ? WHERE id = ?",
            (new_slot_count, new_slot_status, new_slot_id)
        )

        # Update booking
        cursor.execute(
            "UPDATE bookings SET slot_id = ? WHERE id = ?",
            (new_slot_id, booking_id)
        )

        # Record booking event
        cursor.execute(
            """
            INSERT INTO booking_events (booking_id, event_type, old_slot_id, new_slot_id, triggered_by_user_id, reason)
            VALUES (?, 'rescheduled', ?, ?, ?, ?)
            """,
            (booking_id, old_slot_id, new_slot_id, admin_user_id, reason)
        )

        cursor.execute("COMMIT;")

        log_audit(
            action="BOOKING_RESCHEDULED",
            entity_type="bookings",
            entity_id=booking_id,
            details=f"Booking {booking_id} moved from slot {old_slot_id} to {new_slot_id}. Reason: {reason}",
            user_id=admin_user_id
        )
        return True, None

    except Exception as e:
        try:
            cursor.execute("ROLLBACK;")
        except Exception:
            pass
        return False, f"Rescheduling failed: {str(e)}"

def get_student_bookings(student_id):
    db = get_db()
    return db.execute(
        """
        SELECT b.*, 
               e.id as exam_id, e.title as exam_title, e.exam_type, e.max_marks, e.booking_end, e.status as exam_status,
               c.code as course_code, c.name as course_name,
               s.slot_date, s.start_time, s.end_time, s.venue_or_link,
               ep.full_name as examiner_name,
               ev.id as evaluation_id, ev.status as evaluation_status, ev.total_score,
               rp.is_published
        FROM bookings b
        JOIN examinations e ON b.examination_id = e.id
        JOIN courses c ON e.course_id = c.id
        JOIN examination_slots s ON b.slot_id = s.id
        JOIN examiner_profiles ep ON s.examiner_id = ep.user_id
        LEFT JOIN evaluations ev ON b.id = ev.booking_id
        LEFT JOIN result_publications rp ON e.id = rp.examination_id
        WHERE b.student_id = ?
        ORDER BY s.slot_date DESC, s.start_time DESC
        """,
        (student_id,)
    ).fetchall()

def get_slot_roster(slot_id):
    """
    Returns list of students booked in a specific slot, along with their evaluation status.
    """
    db = get_db()
    return db.execute(
        """
        SELECT b.id as booking_id, b.status as booking_status, b.booked_at,
               u.id as student_user_id, u.email as student_email,
               sp.student_id_number, sp.full_name as student_name, sp.department, sp.program,
               ev.id as evaluation_id, ev.status as evaluation_status, ev.total_score
        FROM bookings b
        JOIN users u ON b.student_id = u.id
        JOIN student_profiles sp ON u.id = sp.user_id
        LEFT JOIN evaluations ev ON b.id = ev.booking_id
        WHERE b.slot_id = ? AND b.status = 'confirmed'
        ORDER BY sp.student_id_number ASC
        """,
        (slot_id,)
    ).fetchall()

def get_booking_events(booking_id):
    db = get_db()
    return db.execute(
        """
        SELECT be.*, u.username as triggered_by_username
        FROM booking_events be
        JOIN users u ON be.triggered_by_user_id = u.id
        WHERE be.booking_id = ?
        ORDER BY be.created_at ASC
        """,
        (booking_id,)
    ).fetchall()

def get_all_bookings(examination_id=None, status=None, search=None):
    db = get_db()
    query = """
        SELECT b.*, 
               e.title as exam_title, c.code as course_code,
               s.slot_date, s.start_time, s.end_time, s.venue_or_link,
               sp.student_id_number, sp.full_name as student_name,
               ep.full_name as examiner_name
        FROM bookings b
        JOIN examinations e ON b.examination_id = e.id
        JOIN courses c ON e.course_id = c.id
        JOIN examination_slots s ON b.slot_id = s.id
        JOIN student_profiles sp ON b.student_id = sp.user_id
        JOIN examiner_profiles ep ON s.examiner_id = ep.user_id
        WHERE 1=1
    """
    params = []
    if examination_id:
        query += " AND b.examination_id = ?"
        params.append(examination_id)
    if status:
        query += " AND b.status = ?"
        params.append(status)
    if search:
        query += " AND (sp.full_name LIKE ? OR sp.student_id_number LIKE ? OR e.title LIKE ?)"
        wildcard = f"%{search}%"
        params.extend([wildcard, wildcard, wildcard])

    query += " ORDER BY b.booked_at DESC"
    return db.execute(query, params).fetchall()
