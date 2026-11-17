import pytest
from app.services.slot_service import create_slot
from app.services.booking_service import book_examination_slot
from app.services.evaluation_service import save_or_submit_evaluation, publish_exam_results, get_student_published_results
from app.services.rubric_service import calculate_weighted_final_score, get_rubrics_by_exam
from app.services.auth_service import register_examiner, update_examiner_status

def test_rubric_weighted_scoring_formula(app, sample_setup):
    """Verifies the exact PRD weighted rubric formula."""
    with app.app_context():
        exam_id = sample_setup['exam_id']
        rubrics = get_rubrics_by_exam(exam_id)
        # Criterion 1: max 50, weight 50%
        # Criterion 2: max 50, weight 50%
        # Awarded: 40 on crit 1 (ratio 0.8), 30 on crit 2 (ratio 0.6)
        # Total ratio = (0.8 * 50 + 0.6 * 50) / 100 = 70%
        # Final score = 70% * 100 max marks = 70.0
        marks_map = {rubrics[0]['id']: 40.0, rubrics[1]['id']: 30.0}
        final_score = calculate_weighted_final_score(rubrics, marks_map, 100.0)
        assert final_score == 70.0

def test_marks_validation_and_bounds(app, sample_setup):
    """FR-EX-08: Validate criterion marks are non-negative and do not exceed criterion maximum."""
    with app.app_context():
        exam_id = sample_setup['exam_id']
        ex_id = sample_setup['examiner_id']
        st_id = sample_setup['student_id']
        r_ids = sample_setup['rubric_ids']

        slot_id, _ = create_slot(exam_id, ex_id, "2026-11-20", "10:00", "12:00", "Lab 1", 2, bypass_window_check=True)
        b_id, _ = book_examination_slot(st_id, exam_id, slot_id)

        # Test negative marks
        marks_neg = {str(r_ids[0]): -5.0, str(r_ids[1]): 30.0}
        _, err_neg = save_or_submit_evaluation(b_id, ex_id, marks_neg, {}, "Remarks", is_submit=True)
        assert err_neg is not None
        assert "cannot be negative" in err_neg

        # Test marks exceeding criterion max (criterion max is 50.0)
        marks_excess = {str(r_ids[0]): 60.0, str(r_ids[1]): 30.0}
        _, err_excess = save_or_submit_evaluation(b_id, ex_id, marks_excess, {}, "Remarks", is_submit=True)
        assert err_excess is not None
        assert "exceed criterion maximum" in err_excess

def test_examiner_slot_authorization(app, sample_setup):
    """BR-09: Examiner evaluates only students booked in their own assigned slots."""
    with app.app_context():
        exam_id = sample_setup['exam_id']
        ex1_id = sample_setup['examiner_id']
        st_id = sample_setup['student_id']
        r_ids = sample_setup['rubric_ids']
        admin_id = sample_setup['admin_id']

        # Register examiner 2
        ex2_id, _ = register_examiner("ex_other", "other@test.edu", "Pass@123", "EMP02", "Dr. Other", "CS", "Prof")
        update_examiner_status(ex2_id, 'approved', admin_id)

        # Slot belongs to examiner 1
        slot_id, _ = create_slot(exam_id, ex1_id, "2026-11-20", "10:00", "12:00", "Lab 1", 2, bypass_window_check=True)
        b_id, _ = book_examination_slot(st_id, exam_id, slot_id)

        # Examiner 2 attempts to evaluate -> Unauthorized
        marks_valid = {str(r_ids[0]): 40.0, str(r_ids[1]): 35.0}
        _, err = save_or_submit_evaluation(b_id, ex2_id, marks_valid, {}, "Remarks", is_submit=True)
        assert err is not None
        assert "Unauthorized" in err

def test_result_visibility_only_after_publication(app, sample_setup):
    """BR-11 & FR-ST-09: Students can see results and feedback only after administrator publication."""
    with app.app_context():
        exam_id = sample_setup['exam_id']
        ex_id = sample_setup['examiner_id']
        st_id = sample_setup['student_id']
        r_ids = sample_setup['rubric_ids']
        admin_id = sample_setup['admin_id']

        slot_id, _ = create_slot(exam_id, ex_id, "2026-11-20", "10:00", "12:00", "Lab 1", 2, bypass_window_check=True)
        b_id, _ = book_examination_slot(st_id, exam_id, slot_id)

        # Submit evaluation
        marks = {str(r_ids[0]): 45.0, str(r_ids[1]): 40.0}
        save_or_submit_evaluation(b_id, ex_id, marks, {}, "Great performance", is_submit=True)

        # Results NOT published yet -> Student results list must be empty
        results_before = get_student_published_results(st_id)
        assert len(results_before) == 0

        # Admin publishes results
        publish_exam_results(exam_id, admin_id, "Grades Released")

        # Now student can view result
        results_after = get_student_published_results(st_id)
        assert len(results_after) == 1
        assert results_after[0]['total_score'] == 85.0
