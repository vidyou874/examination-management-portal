-- Examination Management Portal (EMP) SQLite Schema
PRAGMA foreign_keys = ON;

-- 1. Users table
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username VARCHAR(80) UNIQUE NOT NULL,
    email VARCHAR(120) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role VARCHAR(20) NOT NULL CHECK(role IN ('admin', 'examiner', 'student')),
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 2. Student Profiles
CREATE TABLE IF NOT EXISTS student_profiles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER UNIQUE NOT NULL,
    student_id_number VARCHAR(50) UNIQUE NOT NULL,
    full_name VARCHAR(120) NOT NULL,
    department VARCHAR(100) NOT NULL,
    program VARCHAR(100) NOT NULL,
    phone VARCHAR(30),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- 3. Examiner Profiles
CREATE TABLE IF NOT EXISTS examiner_profiles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER UNIQUE NOT NULL,
    employee_id VARCHAR(50) UNIQUE NOT NULL,
    full_name VARCHAR(120) NOT NULL,
    department VARCHAR(100) NOT NULL,
    designation VARCHAR(100) NOT NULL,
    phone VARCHAR(30),
    approval_status VARCHAR(20) NOT NULL DEFAULT 'pending' CHECK(approval_status IN ('pending', 'approved', 'rejected')),
    approved_at TIMESTAMP,
    approved_by INTEGER,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (approved_by) REFERENCES users(id) ON DELETE SET NULL
);

-- 4. Courses
CREATE TABLE IF NOT EXISTS courses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code VARCHAR(20) UNIQUE NOT NULL,
    name VARCHAR(150) NOT NULL,
    description TEXT,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 5. Examinations
CREATE TABLE IF NOT EXISTS examinations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    course_id INTEGER NOT NULL,
    title VARCHAR(150) NOT NULL,
    exam_type VARCHAR(50) NOT NULL,
    duration_minutes INTEGER NOT NULL,
    max_marks REAL NOT NULL,
    slot_creation_start TIMESTAMP NOT NULL,
    slot_creation_end TIMESTAMP NOT NULL,
    booking_start TIMESTAMP NOT NULL,
    booking_end TIMESTAMP NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'draft' CHECK(status IN ('draft', 'slot_creation', 'booking_open', 'closed', 'completed')),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (course_id) REFERENCES courses(id) ON DELETE RESTRICT
);

-- 6. Examiner Assignments
CREATE TABLE IF NOT EXISTS examiner_assignments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    examination_id INTEGER NOT NULL,
    examiner_id INTEGER NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1,
    assigned_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(examination_id, examiner_id),
    FOREIGN KEY (examination_id) REFERENCES examinations(id) ON DELETE CASCADE,
    FOREIGN KEY (examiner_id) REFERENCES users(id) ON DELETE CASCADE
);

-- 7. Examination Rubrics
CREATE TABLE IF NOT EXISTS examination_rubrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    examination_id INTEGER NOT NULL,
    criterion_name VARCHAR(120) NOT NULL,
    description TEXT,
    max_marks REAL NOT NULL,
    weightage REAL NOT NULL, -- percentage e.g. 25.0
    display_order INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (examination_id) REFERENCES examinations(id) ON DELETE CASCADE
);

-- 8. Examination Slots
CREATE TABLE IF NOT EXISTS examination_slots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    examination_id INTEGER NOT NULL,
    examiner_id INTEGER NOT NULL,
    slot_date DATE NOT NULL,
    start_time TIME NOT NULL,
    end_time TIME NOT NULL,
    venue_or_link VARCHAR(150) NOT NULL,
    capacity INTEGER NOT NULL CHECK(capacity > 0),
    booked_count INTEGER NOT NULL DEFAULT 0 CHECK(booked_count >= 0),
    status VARCHAR(20) NOT NULL DEFAULT 'available' CHECK(status IN ('available', 'full', 'cancelled')),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (examination_id) REFERENCES examinations(id) ON DELETE RESTRICT,
    FOREIGN KEY (examiner_id) REFERENCES users(id) ON DELETE RESTRICT
);

-- 9. Bookings
CREATE TABLE IF NOT EXISTS bookings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    examination_id INTEGER NOT NULL,
    slot_id INTEGER NOT NULL,
    student_id INTEGER NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'confirmed' CHECK(status IN ('confirmed', 'cancelled', 'rescheduled')),
    booked_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    cancelled_at TIMESTAMP,
    cancellation_reason TEXT,
    FOREIGN KEY (examination_id) REFERENCES examinations(id) ON DELETE RESTRICT,
    FOREIGN KEY (slot_id) REFERENCES examination_slots(id) ON DELETE RESTRICT,
    FOREIGN KEY (student_id) REFERENCES users(id) ON DELETE RESTRICT
);

-- Unique index to prevent duplicate active bookings for the same exam
CREATE UNIQUE INDEX IF NOT EXISTS idx_unique_active_booking 
ON bookings(examination_id, student_id) 
WHERE status = 'confirmed';

-- 10. Booking Events (Audit of bookings, cancellations, rescheduling)
CREATE TABLE IF NOT EXISTS booking_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    booking_id INTEGER NOT NULL,
    event_type VARCHAR(20) NOT NULL CHECK(event_type IN ('booked', 'cancelled', 'rescheduled')),
    old_slot_id INTEGER,
    new_slot_id INTEGER,
    triggered_by_user_id INTEGER NOT NULL,
    reason TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (booking_id) REFERENCES bookings(id) ON DELETE CASCADE,
    FOREIGN KEY (old_slot_id) REFERENCES examination_slots(id) ON DELETE SET NULL,
    FOREIGN KEY (new_slot_id) REFERENCES examination_slots(id) ON DELETE SET NULL,
    FOREIGN KEY (triggered_by_user_id) REFERENCES users(id) ON DELETE RESTRICT
);

-- 11. Evaluations
CREATE TABLE IF NOT EXISTS evaluations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    booking_id INTEGER UNIQUE NOT NULL,
    examination_id INTEGER NOT NULL,
    student_id INTEGER NOT NULL,
    examiner_id INTEGER NOT NULL,
    total_score REAL NOT NULL DEFAULT 0.0,
    remarks TEXT,
    status VARCHAR(20) NOT NULL DEFAULT 'draft' CHECK(status IN ('draft', 'submitted')),
    submitted_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (booking_id) REFERENCES bookings(id) ON DELETE RESTRICT,
    FOREIGN KEY (examination_id) REFERENCES examinations(id) ON DELETE RESTRICT,
    FOREIGN KEY (student_id) REFERENCES users(id) ON DELETE RESTRICT,
    FOREIGN KEY (examiner_id) REFERENCES users(id) ON DELETE RESTRICT
);

-- 12. Evaluation Details (Criterion-level breakdown)
CREATE TABLE IF NOT EXISTS evaluation_details (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    evaluation_id INTEGER NOT NULL,
    rubric_id INTEGER NOT NULL,
    marks_awarded REAL NOT NULL CHECK(marks_awarded >= 0),
    criterion_remarks TEXT,
    FOREIGN KEY (evaluation_id) REFERENCES evaluations(id) ON DELETE CASCADE,
    FOREIGN KEY (rubric_id) REFERENCES examination_rubrics(id) ON DELETE RESTRICT
);

-- 13. Result Publications
CREATE TABLE IF NOT EXISTS result_publications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    examination_id INTEGER UNIQUE NOT NULL,
    is_published INTEGER NOT NULL DEFAULT 0,
    published_at TIMESTAMP,
    published_by INTEGER,
    notes TEXT,
    FOREIGN KEY (examination_id) REFERENCES examinations(id) ON DELETE CASCADE,
    FOREIGN KEY (published_by) REFERENCES users(id) ON DELETE SET NULL
);

-- 14. Audit Logs
CREATE TABLE IF NOT EXISTS audit_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    action VARCHAR(100) NOT NULL,
    entity_type VARCHAR(50) NOT NULL,
    entity_id INTEGER,
    details TEXT,
    ip_address VARCHAR(45),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
);

-- Indexes for performant lookups
CREATE INDEX IF NOT EXISTS idx_users_role ON users(role);
CREATE INDEX IF NOT EXISTS idx_slots_exam_date ON examination_slots(examination_id, slot_date);
CREATE INDEX IF NOT EXISTS idx_slots_examiner ON examination_slots(examiner_id);
CREATE INDEX IF NOT EXISTS idx_bookings_student ON bookings(student_id);
CREATE INDEX IF NOT EXISTS idx_bookings_slot ON bookings(slot_id);
CREATE INDEX IF NOT EXISTS idx_evaluations_exam ON evaluations(examination_id);
CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_logs(created_at);
