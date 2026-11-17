from app.database import get_db
from app.services.audit_service import log_audit

def get_courses(active_only=False, search=None):
    db = get_db()
    query = """
        SELECT c.*, 
               (SELECT COUNT(*) FROM examinations e WHERE e.course_id = c.id) AS exam_count
        FROM courses c
        WHERE 1=1
    """
    params = []
    if active_only:
        query += " AND c.is_active = 1"
    if search:
        query += " AND (c.code LIKE ? OR c.name LIKE ?)"
        wildcard = f"%{search}%"
        params.extend([wildcard, wildcard])

    query += " ORDER BY c.code ASC"
    return db.execute(query, params).fetchall()

def get_course_by_id(course_id):
    db = get_db()
    return db.execute(
        """
        SELECT c.*,
               (SELECT COUNT(*) FROM examinations e WHERE e.course_id = c.id) AS exam_count
        FROM courses c
        WHERE c.id = ?
        """,
        (course_id,)
    ).fetchone()

def create_course(code, name, description, admin_user_id):
    db = get_db()
    code = code.strip().upper()
    name = name.strip()

    existing = db.execute("SELECT id FROM courses WHERE code = ?", (code,)).fetchone()
    if existing:
        return None, f"Course code '{code}' already exists."

    try:
        cursor = db.cursor()
        cursor.execute(
            """
            INSERT INTO courses (code, name, description, is_active)
            VALUES (?, ?, ?, 1)
            """,
            (code, name, description.strip() if description else None)
        )
        course_id = cursor.lastrowid
        db.commit()

        log_audit(
            action="COURSE_CREATED",
            entity_type="courses",
            entity_id=course_id,
            details=f"Course created: {code} - {name}",
            user_id=admin_user_id
        )
        return course_id, None
    except Exception as e:
        db.rollback()
        return None, str(e)

def update_course(course_id, code, name, description, is_active, admin_user_id):
    db = get_db()
    code = code.strip().upper()
    name = name.strip()

    existing = db.execute(
        "SELECT id FROM courses WHERE code = ? AND id != ?",
        (code, course_id)
    ).fetchone()
    if existing:
        return False, f"Course code '{code}' is already used by another course."

    try:
        db.execute(
            """
            UPDATE courses
            SET code = ?, name = ?, description = ?, is_active = ?
            WHERE id = ?
            """,
            (code, name, description.strip() if description else None, 1 if is_active else 0, course_id)
        )
        db.commit()

        log_audit(
            action="COURSE_UPDATED",
            entity_type="courses",
            entity_id=course_id,
            details=f"Course updated: {code} (active={is_active})",
            user_id=admin_user_id
        )
        return True, None
    except Exception as e:
        db.rollback()
        return False, str(e)

def delete_or_archive_course(course_id, admin_user_id):
    """
    Safely deletes a course if it has no associated exams.
    If examinations exist, archives/deactivates it instead to preserve history.
    """
    db = get_db()
    course = get_course_by_id(course_id)
    if not course:
        return False, "Course not found."

    if course['exam_count'] > 0:
        # Cannot delete due to historical dependencies: archive it
        try:
            db.execute("UPDATE courses SET is_active = 0 WHERE id = ?", (course_id,))
            db.commit()
            log_audit(
                action="COURSE_ARCHIVED",
                entity_type="courses",
                entity_id=course_id,
                details=f"Course {course['code']} archived because it contains {course['exam_count']} examination(s).",
                user_id=admin_user_id
            )
            return True, f"Course '{course['code']}' has linked examinations and was archived (deactivated) to preserve historical records."
        except Exception as e:
            db.rollback()
            return False, str(e)
    else:
        # Safe to delete completely
        try:
            db.execute("DELETE FROM courses WHERE id = ?", (course_id,))
            db.commit()
            log_audit(
                action="COURSE_DELETED",
                entity_type="courses",
                entity_id=course_id,
                details=f"Course {course['code']} permanently deleted.",
                user_id=admin_user_id
            )
            return True, f"Course '{course['code']}' was deleted."
        except Exception as e:
            db.rollback()
            return False, str(e)
