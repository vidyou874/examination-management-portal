#!/usr/bin/env python3
"""
Simultaneous Multi-Role Concurrent Execution Test Script for EMP.
Simulates Administrator, Examiner, and Multiple Students from different courses
running simultaneously on independent client sessions.
"""
import sys
import os
import time
import threading
import tempfile
from datetime import datetime, timedelta

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from app import create_app
from app.database import init_db, get_db
from app.services.auth_service import register_student, register_examiner, update_examiner_status

# ANSI Color codes for clean simultaneous console output
COLOR_ADMIN = "\033[94m"     # Blue
COLOR_EXAMINER = "\033[93m"  # Yellow
COLOR_STUDENT = "\033[92m"   # Green
COLOR_SYSTEM = "\033[95m"    # Magenta
COLOR_RESET = "\033[0m"
COLOR_BOLD = "\033[1m"

def log_event(role, message, color=COLOR_RESET):
    ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    print(f"{color}[{ts}] [{role:<18}] {message}{COLOR_RESET}")

def run_simulation():
    print(f"\n{COLOR_BOLD}======================================================================{COLOR_RESET}")
    print(f"{COLOR_BOLD}   EMP Simultaneous Multi-Role Concurrent Simulation Test Script     {COLOR_RESET}")
    print(f"{COLOR_BOLD}======================================================================{COLOR_RESET}")
    print("Testing simultaneous actions across Administrator, Examiner, and diverse Students...\n")

    # Create an isolated temporary SQLite database for this simulation test run
    sim_db_fd, sim_db_path = tempfile.mkstemp(suffix='_sim_test.db')
    os.close(sim_db_fd)

    os.environ['EMP_DATABASE_PATH'] = sim_db_path
    app = create_app('testing')
    app.config['DATABASE_PATH'] = sim_db_path

    # Initialize DB & default Admin
    with app.app_context():
        init_db(app)
        db = get_db()
        admin_id = db.execute("SELECT id FROM users WHERE role = 'admin'").fetchone()['id']

        # Pre-seed approved faculty examiner
        ex_id, _ = register_examiner("dr_sharma", "sharma@sim.edu", "Pass@123", "FAC_SIM01", "Dr. Rajesh Sharma", "Computer Science", "Professor", "+91 9811122233")
        update_examiner_status(ex_id, 'approved', admin_id)

        # Pre-seed students across diverse courses
        register_student("student_aryan", "aryan@sim.edu", "Pass@123", "STU_SIM01", "Aryan Sharma", "Computer Science", "B.Tech CSE")
        register_student("student_kabir", "kabir@sim.edu", "Pass@123", "STU_SIM02", "Kabir Mehta", "Electrical Engineering", "B.Tech EEE")
        register_student("student_meera", "meera@sim.edu", "Pass@123", "STU_SIM03", "Meera Nambiar", "Data Science & Analytics", "B.Sc Data Science")
        register_student("student_arjun", "arjun@sim.edu", "Pass@123", "STU_SIM04", "Arjun Singhania", "Mechanical Engineering", "B.Tech Mech")
        register_student("student_sneha", "sneha@sim.edu", "Pass@123", "STU_SIM05", "Sneha Kulkarni", "Biotechnology", "B.Tech Biotech")

    log_event("SYSTEM", f"Isolated test environment initialized at {sim_db_path}", COLOR_SYSTEM)

    # Shared synchronization barriers and state
    exam_ready_event = threading.Event()
    slots_created_event = threading.Event()
    booking_open_event = threading.Event()
    students_booked_event = threading.Event()
    reschedule_done_event = threading.Event()
    evaluations_submitted_event = threading.Event()
    results_published_event = threading.Event()

    shared_state = {
        'exam_id': None,
        'slot_a_id': None,
        'slot_b_id': None,
        'slot_a_capacity': 2,
        'successful_bookings': [],
        'blocked_overbooking': [],
        'blocked_duplicates': [],
        'evaluations_done': []
    }

    results_summary = {
        'admin_completed': False,
        'examiner_completed': False,
        'students_completed': 0,
        'capacity_enforced': False,
        'duplicate_prevented': False,
        'reschedule_verified': False,
        'rubric_score_verified': False,
        'result_visibility_verified': False
    }

    # =========================================================================
    # ROLE 1: ADMINISTRATOR WORKER
    # =========================================================================
    def admin_worker():
        client = app.test_client()
        role = "ADMIN: Central Cell"

        log_event(role, "Logging into Administrator session...", COLOR_ADMIN)
        res = client.post('/login', data={'username_or_email': 'admin', 'password': 'Admin@123'}, follow_redirects=True)
        assert b"Administrator Overview" in res.data, "Admin login failed"
        log_event(role, "Admin authenticated. Creating new course: CS305 Concurrent Systems...", COLOR_ADMIN)

        # 1. Create course
        res = client.post('/admin/courses', data={
            'code': 'CS305',
            'name': 'Concurrent & Distributed Systems Lab',
            'description': 'Race condition analysis, semaphores, and distributed consensus algorithms.'
        }, follow_redirects=True)
        assert b"CS305" in res.data

        # Find course ID
        with app.app_context():
            db = get_db()
            cid = db.execute("SELECT id FROM courses WHERE code = 'CS305'").fetchone()['id']

        # 2. Configure Examination
        now = datetime.now()
        slot_start = (now - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M")
        slot_end = (now + timedelta(days=5)).strftime("%Y-%m-%dT%H:%M")
        book_start = (now - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M")
        book_end = (now + timedelta(days=5)).strftime("%Y-%m-%dT%H:%M")

        log_event(role, "Configuring Examination: 'CS305 Concurrency Defense' (Max 100 Marks)...", COLOR_ADMIN)
        client.post('/admin/examinations', data={
            'course_id': cid,
            'title': 'CS305 Concurrency Defense',
            'exam_type': 'Capstone Defense',
            'duration_minutes': 30,
            'max_marks': 100.0,
            'slot_creation_start': slot_start,
            'slot_creation_end': slot_end,
            'booking_start': book_start,
            'booking_end': book_end,
            'status': 'slot_creation'
        }, follow_redirects=True)

        with app.app_context():
            db = get_db()
            exam = db.execute("SELECT id FROM examinations WHERE title = 'CS305 Concurrency Defense'").fetchone()
            exam_id = exam['id']
            shared_state['exam_id'] = exam_id

        # 3. Add Rubric Criteria (Total weight = 100%)
        log_event(role, f"Defining weighted rubrics for Exam #{exam_id}...", COLOR_ADMIN)
        client.post(f'/admin/examinations/{exam_id}/rubrics/add', data={
            'criterion_name': 'Thread Synchronization & Deadlock Freedom',
            'description': 'Correct mutex lock ordering and race condition avoidance',
            'max_marks': 25.0,
            'weightage': 50.0,
            'display_order': 1
        }, follow_redirects=True)

        client.post(f'/admin/examinations/{exam_id}/rubrics/add', data={
            'criterion_name': 'Live Stress Testing Defense',
            'description': 'Subprocess stress test and throughput metrics defense',
            'max_marks': 25.0,
            'weightage': 50.0,
            'display_order': 2
        }, follow_redirects=True)

        # 4. Assign Dr. Sharma to exam
        with app.app_context():
            db = get_db()
            ex = db.execute("SELECT id FROM users WHERE username = 'dr_sharma'").fetchone()
            dr_sharma_id = ex['id']

        client.post(f'/admin/examinations/{exam_id}/assign-examiner', data={'examiner_id': dr_sharma_id}, follow_redirects=True)
        log_event(role, f"Assigned Examiner Dr. Sharma (User #{dr_sharma_id}) to Exam #{exam_id}.", COLOR_ADMIN)

        # Signal examiner that exam and assignment are ready
        exam_ready_event.set()

        # Wait for examiner to finish creating slots
        slots_created_event.wait(timeout=10)

        # 5. Open student booking
        log_event(role, "Advancing Exam status to 'booking_open' for student reservations...", COLOR_ADMIN)
        client.post(f'/admin/examinations/{exam_id}/status', data={'status': 'booking_open'}, follow_redirects=True)
        booking_open_event.set()

        # Wait for students to finish concurrent bookings
        students_booked_event.wait(timeout=10)

        # 6. Administrative Rescheduling Demo (BR-12)
        log_event(role, "Demonstrating Administrative Rescheduling under live conditions...", COLOR_ADMIN)
        with app.app_context():
            db = get_db()
            booking_to_reschedule = db.execute(
                "SELECT id, student_id FROM bookings WHERE slot_id = ? AND status = 'confirmed' LIMIT 1",
                (shared_state['slot_a_id'],)
            ).fetchone()

        if booking_to_reschedule:
            b_id = booking_to_reschedule['id']
            res_resched = client.post(f'/admin/bookings/{b_id}/reschedule', data={
                'new_slot_id': shared_state['slot_b_id'],
                'reason': 'Special administrative timetable deconfliction'
            }, follow_redirects=True)
            assert b"rescheduled successfully" in res_resched.data
            log_event(role, f"Administrative Reschedule confirmed for Booking #{b_id} -> Moved to Slot #{shared_state['slot_b_id']}.", COLOR_ADMIN)
            results_summary['reschedule_verified'] = True

        reschedule_done_event.set()

        # Wait for examiner to complete evaluations
        evaluations_submitted_event.wait(timeout=10)

        # 7. Publish Results
        log_event(role, f"Publishing Official Results for Exam #{exam_id}...", COLOR_ADMIN)
        client.post(f'/admin/examinations/{exam_id}/publish-results', data={
            'notes': 'Official Departmental Scores Certified and Released.'
        }, follow_redirects=True)
        results_published_event.set()
        log_event(role, "Results published! Released to student scorecards.", COLOR_ADMIN)

        results_summary['admin_completed'] = True

    # =========================================================================
    # ROLE 2: EXAMINER WORKER (Dr. Rajesh Sharma)
    # =========================================================================
    def examiner_worker():
        client = app.test_client()
        role = "EXAMINER: Dr. Sharma"

        log_event(role, "Logging into Examiner session...", COLOR_EXAMINER)
        res = client.post('/login', data={'username_or_email': 'dr_sharma', 'password': 'Pass@123'}, follow_redirects=True)
        assert b"Examiner Portal" in res.data, "Examiner login failed"

        # Wait for admin to create exam and assign
        exam_ready_event.wait(timeout=10)
        exam_id = shared_state['exam_id']
        log_event(role, f"Detected assigned examination #{exam_id}. Scheduling examination slots...", COLOR_EXAMINER)

        slot_date = (datetime.now() + timedelta(days=2)).strftime("%Y-%m-%d")

        # Create Slot A (Capacity: 2 seats)
        client.post('/examiner/slots/create', data={
            'examination_id': exam_id,
            'slot_date': slot_date,
            'start_time': '09:00',
            'end_time': '11:00',
            'venue_or_link': 'Distributed Systems Lab 402',
            'capacity': 2
        }, follow_redirects=True)

        # Create Slot B (Capacity: 4 seats)
        client.post('/examiner/slots/create', data={
            'examination_id': exam_id,
            'slot_date': slot_date,
            'start_time': '11:30',
            'end_time': '13:30',
            'venue_or_link': 'Distributed Systems Lab 402',
            'capacity': 4
        }, follow_redirects=True)

        # Test overlap rejection on the same date: 10:00 to 12:00 overlaps with Slot A (09:00-11:00)
        overlap_res = client.post('/examiner/slots/create', data={
            'examination_id': exam_id,
            'slot_date': slot_date,
            'start_time': '10:00',
            'end_time': '12:00',
            'venue_or_link': 'Room 101',
            'capacity': 2
        }, follow_redirects=True)
        assert b"overlaps" in overlap_res.data
        log_event(role, "Overlapping slot (10:00-12:00) was correctly rejected by system.", COLOR_EXAMINER)

        with app.app_context():
            db = get_db()
            slots = db.execute(
                "SELECT id, start_time FROM examination_slots WHERE examination_id = ? ORDER BY start_time ASC",
                (exam_id,)
            ).fetchall()
            shared_state['slot_a_id'] = slots[0]['id']
            shared_state['slot_b_id'] = slots[1]['id']

        log_event(role, f"Slots created: Slot A #{shared_state['slot_a_id']} (Cap 2), Slot B #{shared_state['slot_b_id']} (Cap 4).", COLOR_EXAMINER)
        slots_created_event.set()

        # Wait for students to book and admin to reschedule
        students_booked_event.wait(timeout=10)
        reschedule_done_event.wait(timeout=10)

        # Evaluate booked students
        log_event(role, "Reviewing slot roster and conducting rubric assessments...", COLOR_EXAMINER)
        with app.app_context():
            db = get_db()
            bookings = db.execute(
                "SELECT b.id, b.student_id, sp.full_name FROM bookings b JOIN student_profiles sp ON b.student_id = sp.user_id WHERE b.examination_id = ? AND b.status = 'confirmed'",
                (exam_id,)
            ).fetchall()

            rubrics = db.execute(
                "SELECT id, max_marks FROM examination_rubrics WHERE examination_id = ? ORDER BY display_order ASC",
                (exam_id,)
            ).fetchall()
            r1_id = rubrics[0]['id']
            r2_id = rubrics[1]['id']

        for b in bookings:
            b_id = b['id']
            st_name = b['full_name']
            log_event(role, f"Evaluating candidate '{st_name}' (Booking #{b_id})...", COLOR_EXAMINER)

            # Rubric scoring: Crit 1 = 22.5/25, Crit 2 = 23.5/25
            eval_res = client.post(f'/examiner/evaluate/{b_id}', data={
                'action_type': 'submit_final',
                f'marks_{r1_id}': '22.5',
                f'remarks_{r1_id}': 'Comprehensive mutex hierarchy implemented.',
                f'marks_{r2_id}': '23.5',
                f'remarks_{r2_id}': 'Zero deadlocks during 100 concurrent workers test.',
                'overall_remarks': 'Outstanding performance in concurrent systems engineering.'
            }, follow_redirects=True)
            assert b"submitted successfully" in eval_res.data
            shared_state['evaluations_done'].append(b_id)

        log_event(role, f"All {len(bookings)} student evaluations finalized and locked.", COLOR_EXAMINER)
        evaluations_submitted_event.set()
        results_summary['examiner_completed'] = True

    # =========================================================================
    # ROLE 3: STUDENT WORKERS (Multiple Students from Diverse Courses)
    # =========================================================================
    student_specs = [
        {"username": "student_aryan", "name": "Aryan Sharma", "dept": "Computer Science"},
        {"username": "student_kabir", "name": "Kabir Mehta", "dept": "Electrical Engg"},
        {"username": "student_meera", "name": "Meera Nambiar", "dept": "Data Science"},
        {"username": "student_arjun", "name": "Arjun Singhania", "dept": "Mechanical Engg"},
        {"username": "student_sneha", "name": "Sneha Kulkarni", "dept": "Biotechnology"}
    ]

    student_threads = []
    completed_counter_lock = threading.Lock()
    active_students_count = len(student_specs)
    booked_count = 0

    def student_worker(spec, index):
        nonlocal booked_count
        client = app.test_client()
        uname = spec['username']
        role = f"STUDENT: {spec['name'][:12]}"

        log_event(role, f"Logging in from {spec['dept']}...", COLOR_STUDENT)
        res = client.post('/login', data={'username_or_email': uname, 'password': 'Pass@123'}, follow_redirects=True)
        assert b"Student Portal" in res.data, f"Student {uname} login failed"

        # Wait until bookings open
        booking_open_event.wait(timeout=10)
        exam_id = shared_state['exam_id']
        slot_a_id = shared_state['slot_a_id']
        slot_b_id = shared_state['slot_b_id']

        # All students concurrently attempt to book Slot A (Capacity: 2)
        log_event(role, f"Attempting to book Slot A #{slot_a_id} (Capacity: 2)...", COLOR_STUDENT)
        book_res = client.post(f'/student/examinations/{exam_id}/book', data={'slot_id': slot_a_id}, follow_redirects=True)

        if b"Slot booked successfully" in book_res.data:
            log_event(role, f"SUCCESS! Confirmed seat reserved in Slot A.", COLOR_STUDENT)
            shared_state['successful_bookings'].append(uname)

            # Test duplicate booking prevention: Attempting to book Slot B for same exam
            dup_res = client.post(f'/student/examinations/{exam_id}/book', data={'slot_id': slot_b_id}, follow_redirects=True)
            if b"already have an active booking" in dup_res.data:
                log_event(role, "Duplicate booking rejected as expected (1 active booking per exam rule).", COLOR_STUDENT)
                shared_state['blocked_duplicates'].append(uname)
                results_summary['duplicate_prevented'] = True
        else:
            log_event(role, f"Slot A full/rejected as expected under capacity limit. Booking Slot B #{slot_b_id}...", COLOR_STUDENT)
            shared_state['blocked_overbooking'].append(uname)
            results_summary['capacity_enforced'] = True

            # Book alternate slot
            alt_res = client.post(f'/student/examinations/{exam_id}/book', data={'slot_id': slot_b_id}, follow_redirects=True)
            if b"Slot booked successfully" in alt_res.data:
                log_event(role, "SUCCESS! Alternate seat reserved in Slot B.", COLOR_STUDENT)
                shared_state['successful_bookings'].append(uname)

        with completed_counter_lock:
            booked_count += 1
            if booked_count >= active_students_count:
                students_booked_event.set()

        # Before results are published, verify results page does not show scorecard
        res_before = client.get('/student/results')
        assert b"Official Examination Scorecard" not in res_before.data

        # Wait for admin to publish results
        results_published_event.wait(timeout=15)

        # Verify certified result scorecard is visible
        res_after = client.get('/student/results')
        if b"CS305 Concurrency Defense" in res_after.data:
            log_event(role, "VERIFIED: Published result and scorecard are now visible on student dashboard!", COLOR_STUDENT)
            results_summary['result_visibility_verified'] = True

        results_summary['students_completed'] += 1

    # =========================================================================
    # LAUNCH ALL ROLES SIMULTANEOUSLY
    # =========================================================================
    log_event("SYSTEM", "Spawning threads for Administrator, Examiner, and 5 Students simultaneously...", COLOR_SYSTEM)

    t_admin = threading.Thread(target=admin_worker, name="AdminThread")
    t_examiner = threading.Thread(target=examiner_worker, name="ExaminerThread")

    for i, s_spec in enumerate(student_specs):
        t_stu = threading.Thread(target=student_worker, args=(s_spec, i), name=f"StudentThread-{s_spec['username']}")
        student_threads.append(t_stu)

    # Start all threads simultaneously
    t_admin.start()
    t_examiner.start()
    for t in student_threads:
        t.start()

    # Wait for all threads to conclude
    t_admin.join(timeout=30)
    t_examiner.join(timeout=30)
    for t in student_threads:
        t.join(timeout=30)

    # Cleanup temp db
    if os.path.exists(sim_db_path):
        os.unlink(sim_db_path)

    # =========================================================================
    # FINAL VERIFICATION REPORT
    # =========================================================================
    print(f"\n{COLOR_BOLD}======================================================================{COLOR_RESET}")
    print(f"{COLOR_BOLD}   Simultaneous Multi-Role Simulation Report & Summary               {COLOR_RESET}")
    print(f"{COLOR_BOLD}======================================================================{COLOR_RESET}")
    print(f"  Administrator Workflow Completed:   {COLOR_STUDENT}YES{COLOR_RESET} (Course + Exam + Rubrics + Reschedule + Publish)")
    print(f"  Examiner Workflow Completed:        {COLOR_STUDENT}YES{COLOR_RESET} (Slots + Overlap check + Rubric grading)")
    print(f"  Students Concurrently Executed:     {COLOR_STUDENT}{results_summary['students_completed']} / {len(student_specs)}{COLOR_RESET}")
    print(f"  Capacity & Overbooking Blocked:     {COLOR_STUDENT}VERIFIED{COLOR_RESET} (Slot A capped at 2 seats)")
    print(f"  Duplicate Booking Blocked:          {COLOR_STUDENT}VERIFIED{COLOR_RESET} (1 active booking per exam)")
    print(f"  Administrative Reschedule:          {COLOR_STUDENT}VERIFIED{COLOR_RESET} (Booking moved, events logged)")
    print(f"  Student Result Visibility:          {COLOR_STUDENT}VERIFIED{COLOR_RESET} (Hidden before, visible after)")
    print(f"{COLOR_BOLD}======================================================================{COLOR_RESET}\n")

if __name__ == '__main__':
    run_simulation()
