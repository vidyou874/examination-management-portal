import pytest
from app.services.slot_service import create_slot, get_slot_by_id
from app.services.booking_service import book_examination_slot, cancel_booking
from app.services.auth_service import register_student

def test_slot_capacity_and_overbooking_prevention(app, sample_setup):
    """BR-05 & BR-06: Active bookings never exceed capacity. Slot becomes full and rejects extra bookings."""
    with app.app_context():
        exam_id = sample_setup['exam_id']
        ex_id = sample_setup['examiner_id']
        s1 = sample_setup['student_id']

        # Create student 2
        s2, _ = register_student("stu_two", "two@test.edu", "Pass@123", "STU02", "Student Two", "CS", "B.Tech")
        # Create student 3
        s3, _ = register_student("stu_three", "three@test.edu", "Pass@123", "STU03", "Student Three", "CS", "B.Tech")

        # Slot with capacity 2
        slot_id, err = create_slot(exam_id, ex_id, "2026-11-20", "10:00", "12:00", "Lab 1", capacity=2, bypass_window_check=True)
        assert err is None

        # Student 1 books -> Success
        b1, err1 = book_examination_slot(s1, exam_id, slot_id)
        assert err1 is None
        slot = get_slot_by_id(slot_id)
        assert slot['booked_count'] == 1
        assert slot['status'] == 'available'

        # Student 2 books -> Success, slot becomes full
        b2, err2 = book_examination_slot(s2, exam_id, slot_id)
        assert err2 is None
        slot = get_slot_by_id(slot_id)
        assert slot['booked_count'] == 2
        assert slot['status'] == 'full'

        # Student 3 attempts to book -> Rejected: slot is full!
        b3, err3 = book_examination_slot(s3, exam_id, slot_id)
        assert b3 is None
        assert "full" in err3.lower()

def test_duplicate_booking_prevention(app, sample_setup):
    """BR-07: A student may have at most one active booking per examination."""
    with app.app_context():
        exam_id = sample_setup['exam_id']
        ex_id = sample_setup['examiner_id']
        s1 = sample_setup['student_id']

        # Create two distinct slots for the same exam
        slot1_id, _ = create_slot(exam_id, ex_id, "2026-11-20", "09:00", "11:00", "Lab 1", capacity=5, bypass_window_check=True)
        slot2_id, _ = create_slot(exam_id, ex_id, "2026-11-20", "12:00", "14:00", "Lab 2", capacity=5, bypass_window_check=True)

        # Student books slot 1
        b1, err1 = book_examination_slot(s1, exam_id, slot1_id)
        assert err1 is None

        # Student attempts to book slot 2 for the same exam -> Must fail
        b2, err2 = book_examination_slot(s1, exam_id, slot2_id)
        assert b2 is None
        assert "already have an active booking" in err2

def test_cancellation_restores_capacity_and_allows_rebooking(app, sample_setup):
    """BR-06 & FR-ST-06: Cancellation restores capacity and allows booking another slot."""
    with app.app_context():
        exam_id = sample_setup['exam_id']
        ex_id = sample_setup['examiner_id']
        s1 = sample_setup['student_id']

        slot1_id, _ = create_slot(exam_id, ex_id, "2026-11-20", "09:00", "11:00", "Lab 1", capacity=1, bypass_window_check=True)
        slot2_id, _ = create_slot(exam_id, ex_id, "2026-11-20", "14:00", "16:00", "Lab 2", capacity=2, bypass_window_check=True)

        # Book slot 1 -> becomes full
        b1, _ = book_examination_slot(s1, exam_id, slot1_id)
        assert get_slot_by_id(slot1_id)['status'] == 'full'

        # Cancel booking 1
        ok, err = cancel_booking(b1, s1, reason="Change of plans")
        assert ok is True

        # Verify slot 1 is available again and booked_count is 0
        slot1 = get_slot_by_id(slot1_id)
        assert slot1['booked_count'] == 0
        assert slot1['status'] == 'available'

        # Now student can book slot 2 successfully
        b2, err2 = book_examination_slot(s1, exam_id, slot2_id)
        assert err2 is None
        assert b2 is not None
