import pytest
from app.services.slot_service import create_slot, get_slot_by_id
from app.services.booking_service import book_examination_slot, admin_reschedule_booking, get_booking_events
from app.services.course_service import delete_or_archive_course, get_course_by_id

def test_examiner_slot_overlap_prevention(app, sample_setup):
    """Slot service prevents the same examiner from having overlapping time slots on the same date."""
    with app.app_context():
        exam_id = sample_setup['exam_id']
        ex_id = sample_setup['examiner_id']

        # Slot 1: 10:00 to 12:00
        s1, err1 = create_slot(exam_id, ex_id, "2026-11-25", "10:00", "12:00", "Room A", 5, bypass_window_check=True)
        assert err1 is None

        # Overlapping slot: 11:00 to 13:00 -> Must be rejected
        s2, err2 = create_slot(exam_id, ex_id, "2026-11-25", "11:00", "13:00", "Room B", 5, bypass_window_check=True)
        assert s2 is None
        assert "overlaps" in err2.lower()

        # Non-overlapping slot: 13:00 to 15:00 -> Allowed
        s3, err3 = create_slot(exam_id, ex_id, "2026-11-25", "13:00", "15:00", "Room B", 5, bypass_window_check=True)
        assert err3 is None
        assert s3 is not None

def test_admin_rescheduling_and_audit_trail(app, sample_setup):
    """BR-12: Administrative reschedule validates target slot capacity, updates counts, and logs booking events."""
    with app.app_context():
        exam_id = sample_setup['exam_id']
        ex_id = sample_setup['examiner_id']
        st_id = sample_setup['student_id']
        admin_id = sample_setup['admin_id']

        slot1, _ = create_slot(exam_id, ex_id, "2026-11-20", "09:00", "10:00", "Room 1", capacity=1, bypass_window_check=True)
        slot2, _ = create_slot(exam_id, ex_id, "2026-11-20", "11:00", "12:00", "Room 2", capacity=2, bypass_window_check=True)

        # Student books slot 1 -> slot 1 becomes full
        b_id, _ = book_examination_slot(st_id, exam_id, slot1)
        assert get_slot_by_id(slot1)['status'] == 'full'

        # Admin reschedules to slot 2
        ok, err = admin_reschedule_booking(b_id, slot2, admin_id, reason="Timetable conflict resolution")
        assert ok is True

        # Verify old slot count decremented and available
        s1_after = get_slot_by_id(slot1)
        assert s1_after['booked_count'] == 0
        assert s1_after['status'] == 'available'

        # Verify new slot count incremented
        s2_after = get_slot_by_id(slot2)
        assert s2_after['booked_count'] == 1

        # Check booking events audit trail
        events = get_booking_events(b_id)
        assert len(events) >= 2  # 'booked', then 'rescheduled'
        event_types = [e['event_type'] for e in events]
        assert 'rescheduled' in event_types

def test_course_archival_when_dependencies_exist(app, sample_setup):
    """BR-13: Courses referenced by examinations are deactivated/archived rather than deleted."""
    with app.app_context():
        cid = sample_setup['course_id']
        admin_id = sample_setup['admin_id']

        # Attempt to delete course with linked exam
        ok, msg = delete_or_archive_course(cid, admin_id)
        assert ok is True
        assert "archived" in msg.lower()

        # Verify course still exists in DB but is_active = 0
        c = get_course_by_id(cid)
        assert c is not None
        assert c['is_active'] == 0
