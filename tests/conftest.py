import pytest
import os
import tempfile
from app import create_app
from app.database import init_db, get_db
from app.services.auth_service import register_student, register_examiner, update_examiner_status
from app.services.course_service import create_course
from app.services.exam_service import create_examination, assign_examiner_to_exam
from app.services.rubric_service import add_rubric_criterion
from app.services.slot_service import create_slot

@pytest.fixture
def app():
    # Create temporary file for SQLite testing database
    db_fd, db_path = tempfile.mkstemp(suffix='.db')
    os.close(db_fd)

    app = create_app('testing')
    app.config['DATABASE_PATH'] = db_path

    with app.app_context():
        init_db(app)

    yield app

    # Cleanup temp file
    if os.path.exists(db_path):
        os.unlink(db_path)

@pytest.fixture
def client(app):
    return app.test_client()

@pytest.fixture
def db(app):
    with app.app_context():
        yield get_db(app.config['DATABASE_PATH'])

@pytest.fixture
def admin_client(client, app):
    """Logs in as default administrator"""
    client.post('/login', data={'username_or_email': 'admin', 'password': 'Admin@123'}, follow_redirects=True)
    return client

@pytest.fixture
def sample_setup(app):
    """Sets up a course, exam, approved examiner, and student for tests"""
    with app.app_context():
        db = get_db()
        admin = db.execute("SELECT id FROM users WHERE role = 'admin'").fetchone()
        admin_id = admin['id']

        # Course
        cid, _ = create_course("CS101", "Data Structures", "Core CS", admin_id)

        # Examiner (approved)
        ex_id, _ = register_examiner("ex_test", "ex@test.edu", "Pass@123", "EMP01", "Dr. Test Examiner", "CS", "Prof")
        update_examiner_status(ex_id, 'approved', admin_id)

        # Student
        st_id, _ = register_student("st_test", "st@test.edu", "Pass@123", "STU01", "Test Student", "CS", "B.Tech")

        # Exam with status booking_open
        exam_id, _ = create_examination(
            course_id=cid,
            title="CS101 Practical",
            exam_type="Practical",
            duration_minutes=30,
            max_marks=100.0,
            slot_creation_start="2026-01-01 00:00:00",
            slot_creation_end="2026-12-31 23:59:59",
            booking_start="2026-01-01 00:00:00",
            booking_end="2026-12-31 23:59:59",
            status="booking_open",
            admin_user_id=admin_id
        )

        # Rubrics: 2 criteria, each 50%
        r1, _ = add_rubric_criterion(exam_id, "Implementation", "Code quality", 50.0, 50.0, 1, admin_id)
        r2, _ = add_rubric_criterion(exam_id, "Viva", "Oral defense", 50.0, 50.0, 2, admin_id)

        # Assign examiner
        assign_examiner_to_exam(exam_id, ex_id, admin_id)

        return {
            'admin_id': admin_id,
            'course_id': cid,
            'examiner_id': ex_id,
            'student_id': st_id,
            'exam_id': exam_id,
            'rubric_ids': [r1, r2]
        }
