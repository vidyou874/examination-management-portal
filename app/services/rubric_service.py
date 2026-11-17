from app.database import get_db
from app.services.audit_service import log_audit

def get_rubrics_by_exam(examination_id):
    db = get_db()
    return db.execute(
        """
        SELECT * FROM examination_rubrics
        WHERE examination_id = ?
        ORDER BY display_order ASC, id ASC
        """,
        (examination_id,)
    ).fetchall()

def get_rubric_by_id(rubric_id):
    db = get_db()
    return db.execute(
        "SELECT * FROM examination_rubrics WHERE id = ?",
        (rubric_id,)
    ).fetchone()

def add_rubric_criterion(examination_id, criterion_name, description, max_marks, weightage, display_order=0, admin_user_id=None):
    db = get_db()
    try:
        max_marks = float(max_marks)
        weightage = float(weightage)
        if max_marks <= 0:
            return None, "Criterion maximum marks must be greater than zero."
        if weightage <= 0 or weightage > 100:
            return None, "Weightage must be between 0 and 100%."

        # Check total weightage
        current_total = get_total_weightage(examination_id)
        if current_total + weightage > 100.01:
            return None, f"Total weightage would exceed 100% (Current: {current_total}%, Adding: {weightage}%)."

        cursor = db.cursor()
        cursor.execute(
            """
            INSERT INTO examination_rubrics (examination_id, criterion_name, description, max_marks, weightage, display_order)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (examination_id, criterion_name.strip(), description.strip() if description else None, max_marks, weightage, display_order)
        )
        rubric_id = cursor.lastrowid
        db.commit()

        log_audit(
            action="RUBRIC_CRITERION_ADDED",
            entity_type="examination_rubrics",
            entity_id=rubric_id,
            details=f"Rubric '{criterion_name}' added to exam {examination_id} (weight={weightage}%)",
            user_id=admin_user_id
        )
        return rubric_id, None
    except Exception as e:
        db.rollback()
        return None, str(e)

def update_rubric_criterion(rubric_id, criterion_name, description, max_marks, weightage, display_order=0, admin_user_id=None):
    db = get_db()
    existing = get_rubric_by_id(rubric_id)
    if not existing:
        return False, "Rubric criterion not found."

    try:
        max_marks = float(max_marks)
        weightage = float(weightage)
        if max_marks <= 0:
            return False, "Criterion maximum marks must be greater than zero."
        if weightage <= 0 or weightage > 100:
            return False, "Weightage must be between 0 and 100%."

        # Check total weightage excluding this one
        current_total = get_total_weightage(existing['examination_id'], exclude_rubric_id=rubric_id)
        if current_total + weightage > 100.01:
            return False, f"Total weightage would exceed 100% (Other criteria: {current_total}%, New: {weightage}%)."

        db.execute(
            """
            UPDATE examination_rubrics
            SET criterion_name = ?, description = ?, max_marks = ?, weightage = ?, display_order = ?
            WHERE id = ?
            """,
            (criterion_name.strip(), description.strip() if description else None, max_marks, weightage, display_order, rubric_id)
        )
        db.commit()

        log_audit(
            action="RUBRIC_CRITERION_UPDATED",
            entity_type="examination_rubrics",
            entity_id=rubric_id,
            details=f"Rubric criterion {rubric_id} updated",
            user_id=admin_user_id
        )
        return True, None
    except Exception as e:
        db.rollback()
        return False, str(e)

def delete_rubric_criterion(rubric_id, admin_user_id=None):
    db = get_db()
    existing = get_rubric_by_id(rubric_id)
    if not existing:
        return False, "Rubric criterion not found."

    # Check if any evaluations exist using this rubric
    count = db.execute("SELECT COUNT(*) FROM evaluation_details WHERE rubric_id = ?", (rubric_id,)).fetchone()[0]
    if count > 0:
        return False, "Cannot delete rubric criterion that has already been evaluated for students."

    try:
        db.execute("DELETE FROM examination_rubrics WHERE id = ?", (rubric_id,))
        db.commit()
        log_audit(
            action="RUBRIC_CRITERION_DELETED",
            entity_type="examination_rubrics",
            entity_id=rubric_id,
            details=f"Rubric criterion {rubric_id} deleted from exam {existing['examination_id']}",
            user_id=admin_user_id
        )
        return True, None
    except Exception as e:
        db.rollback()
        return False, str(e)

def get_total_weightage(examination_id, exclude_rubric_id=None):
    db = get_db()
    if exclude_rubric_id:
        row = db.execute(
            "SELECT COALESCE(SUM(weightage), 0.0) FROM examination_rubrics WHERE examination_id = ? AND id != ?",
            (examination_id, exclude_rubric_id)
        ).fetchone()
    else:
        row = db.execute(
            "SELECT COALESCE(SUM(weightage), 0.0) FROM examination_rubrics WHERE examination_id = ?",
            (examination_id,)
        ).fetchone()
    return round(float(row[0]), 2) if row else 0.0

def calculate_weighted_final_score(rubric_records, awarded_marks_map, exam_max_marks):
    """
    Computes final score according to the formula:
    Final score = ( Sum_i [ (Marks awarded_i / Criterion max_i) * Weightage_i ] / 100 ) * Exam max marks
    """
    if not rubric_records:
        return 0.0

    weighted_percentage_sum = 0.0
    for r in rubric_records:
        rid = r['id']
        crit_max = float(r['max_marks'])
        weight = float(r['weightage'])
        marks = float(awarded_marks_map.get(rid, 0.0))

        # Clamp between 0 and crit_max
        marks = max(0.0, min(marks, crit_max))
        criterion_ratio = marks / crit_max if crit_max > 0 else 0.0
        weighted_percentage_sum += criterion_ratio * weight

    final_score = (weighted_percentage_sum / 100.0) * float(exam_max_marks)
    return round(final_score, 2)
