import pytest
from app.database import get_db
from app.services.slot_service import create_slot, cancel_slot
from app.services.booking_service import book_examination_slot
from app.services.exam_service import assign_examiner_to_exam, create_examination
from app.services.auth_service import register_examiner, update_examiner_status

def test_admin_slots_filtering_and_live_refresh(admin_client, sample_setup, app):
    with app.app_context():
        db = get_db()
        admin_id = sample_setup['admin_id']
        cid = sample_setup['course_id']
        ex1_id = sample_setup['examiner_id']
        exam1_id = sample_setup['exam_id']
        st_id = sample_setup['student_id']

        # Setup 2nd examiner
        ex2_id, _ = register_examiner("ex2_test", "ex2@test.edu", "Pass@123", "EMP02", "Dr. Second Examiner", "CS", "Assoc Prof")
        update_examiner_status(ex2_id, 'approved', admin_id)

        # Setup 2nd exam
        exam2_id, _ = create_examination(
            course_id=cid,
            title="CS101 Mid-Sem Viva",
            exam_type="Viva",
            duration_minutes=20,
            max_marks=50.0,
            slot_creation_start="2026-01-01 00:00:00",
            slot_creation_end="2026-12-31 23:59:59",
            booking_start="2026-01-01 00:00:00",
            booking_end="2026-12-31 23:59:59",
            status="booking_open",
            admin_user_id=admin_id
        )

        assign_examiner_to_exam(exam2_id, ex2_id, admin_id)

        # Slot 1: Exam 1, Examiner 1, capacity 1
        s1, _ = create_slot(exam1_id, ex1_id, "2026-11-20", "10:00", "11:00", "Room 101", 1, bypass_window_check=True)
        # Slot 2: Exam 2, Examiner 2, capacity 2
        s2, _ = create_slot(exam2_id, ex2_id, "2026-11-20", "11:00", "12:00", "Room 102", 2, bypass_window_check=True)
        # Slot 3: Exam 1, Examiner 1, capacity 2, cancelled
        s3, _ = create_slot(exam1_id, ex1_id, "2026-11-20", "14:00", "15:00", "Room 103", 2, bypass_window_check=True)
        cancel_slot(s3, admin_id, is_admin=True)

    # 1. Test GET /admin/slots with no filters
    res = admin_client.get('/admin/slots')
    assert res.status_code == 200
    assert "Cache-Control" in res.headers
    assert "no-cache" in res.headers["Cache-Control"]
    html = res.data.decode('utf-8')
    assert "Room 101" in html
    assert "Room 102" in html
    assert "Room 103" in html
    assert "3 Slots Listed" in html

    # 2. Test Filter by Exam 1
    res_exam1 = admin_client.get(f'/admin/slots?examination_id={exam1_id}')
    html_exam1 = res_exam1.data.decode('utf-8')
    assert "Room 101" in html_exam1
    assert "Room 103" in html_exam1
    assert "Room 102" not in html_exam1
    assert "2 Slots Listed" in html_exam1

    # 3. Test Filter by Examiner 2
    res_ex2 = admin_client.get(f'/admin/slots?examiner_id={ex2_id}')
    html_ex2 = res_ex2.data.decode('utf-8')
    assert "Room 102" in html_ex2
    assert "Room 101" not in html_ex2
    assert "1 Slot Listed" in html_ex2

    # 4. Test Filter by Status: available vs full vs cancelled
    res_avail = admin_client.get('/admin/slots?status=available')
    html_avail = res_avail.data.decode('utf-8')
    assert "Room 101" in html_avail
    assert "Room 102" in html_avail
    assert "Room 103" not in html_avail

    res_canc = admin_client.get('/admin/slots?status=cancelled')
    html_canc = res_canc.data.decode('utf-8')
    assert "Room 103" in html_canc
    assert "Room 101" not in html_canc
    assert "Room 102" not in html_canc

    # 5. Book Slot 1 to make it full (1/1)
    with app.app_context():
        book_examination_slot(st_id, exam1_id, s1, bypass_window_check=True)

    # Now verify live refresh: Slot 1 is now full
    res_full = admin_client.get('/admin/slots?status=full')
    html_full = res_full.data.decode('utf-8')
    assert "Room 101" in html_full
    assert "1 / 1 seats booked" in html_full
    assert "Room 102" not in html_full

    # 6. Test Empty state when filter matches nothing
    res_none = admin_client.get(f'/admin/slots?examination_id={exam1_id}&examiner_id={ex2_id}')
    html_none = res_none.data.decode('utf-8')
    assert "No examination slots found" in html_none
    assert "Clear Filters" in html_none

def test_exam_timeline_auto_synchronization(client, sample_setup, app):
    from datetime import datetime, timedelta
    from app.services.exam_service import get_examination_by_id, is_student_booking_allowed, get_examinations
    from app.database import get_db

    now = datetime.now()
    past_10m = (now - timedelta(minutes=10)).strftime("%Y-%m-%d %H:%M:%S")
    future_1d = (now + timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")

    with app.app_context():
        db = get_db()
        # Create an examination directly with status 'slot_creation', but booking_start was 10 minutes ago
        cursor = db.cursor()
        cursor.execute("""
            INSERT INTO examinations (
                course_id, title, exam_type, duration_minutes, max_marks,
                slot_creation_start, slot_creation_end, booking_start, booking_end, status
            ) VALUES (?, 'Timeline Test Exam', 'Midterm Viva', 30, 100.0, ?, ?, ?, ?, 'slot_creation')
        """, (sample_setup['course_id'], past_10m, future_1d, past_10m, future_1d))
        exam_id = cursor.lastrowid
        db.commit()

        # Check is_student_booking_allowed directly
        exam_row = db.execute("SELECT * FROM examinations WHERE id = ?", (exam_id,)).fetchone()
        allowed, msg = is_student_booking_allowed(exam_row)
        assert allowed is True
        assert msg is None

        # Fetch exam via get_examination_by_id and verify it auto-synchronized to 'booking_open'
        synced_exam = get_examination_by_id(exam_id)
        assert synced_exam['status'] == 'booking_open'

    # Login as student and verify student examinations page renders "View Available Slots"
    client.post('/login', data={'username_or_email': 'st_test', 'password': 'Pass@123'}, follow_redirects=True)
    res = client.get('/student/examinations')
    assert res.status_code == 200
    html = res.data.decode('utf-8')
    assert "Timeline Test Exam" in html
    assert "View Available Slots" in html
    assert f"/student/examinations/{exam_id}/slots" in html

