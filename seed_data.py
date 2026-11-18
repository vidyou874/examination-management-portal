#!/usr/bin/env python3
"""
Seed Data Script for Examination Management Portal (EMP).
Populates realistic demo courses, examinations, rubrics, examiners, students
across diverse disciplines, slots, bookings, and published evaluations.
"""
import sys
import os
from datetime import datetime, timedelta

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from app.database import get_db, init_db
from app.services.auth_service import register_student, register_examiner, update_examiner_status
from app.services.course_service import create_course
from app.services.exam_service import create_examination, assign_examiner_to_exam
from app.services.rubric_service import add_rubric_criterion
from app.services.slot_service import create_slot
from app.services.booking_service import book_examination_slot
from app.services.evaluation_service import save_or_submit_evaluation, publish_exam_results

def seed():
    print("=" * 60)
    print("  Populating EMP Database with Comprehensive Multi-Disciplinary Data")
    print("=" * 60)

    # 1. Initialize DB and Admin cleanly
    from app.config import Config
    db_path = Config.DATABASE_PATH
    if os.path.exists(db_path):
        os.remove(db_path)
    init_db()
    db = get_db()
    admin_user = db.execute("SELECT id FROM users WHERE role = 'admin'").fetchone()
    admin_id = admin_user['id']

    # 2. Courses across multiple departments
    print("[1/6] Creating Academic Courses across Disciplines...")
    c1, _ = create_course("CS101", "Data Structures and Algorithms", "Core CS algorithms, abstract data types, complexity analysis, and tree structures.", admin_id)
    c2, _ = create_course("CS201", "Database Management Systems", "Relational algebra, SQL, indexing, concurrency control, and transactions.", admin_id)
    c3, _ = create_course("SE301", "Software Engineering & Architecture", "Software lifecycles, microservices, testing paradigms, and design patterns.", admin_id)
    c4, _ = create_course("AI401", "Machine Learning & Neural Networks", "Supervised models, deep neural architectures, and vision foundations.", admin_id)
    c5, _ = create_course("EE102", "Digital Electronics and Circuit Design", "Combinational and sequential logic, microcontrollers, FPGA synthesis, and PCB design.", admin_id)
    c6, _ = create_course("DS205", "Applied Statistical Computing & Data Science", "Exploratory data analysis, hypothesis testing, Bayesian statistics, and R/Python computing.", admin_id)
    c7, _ = create_course("ME302", "Thermodynamics and Heat Engines Lab", "Applied thermodynamic cycles, entropy analysis, and refrigeration performance testing.", admin_id)
    c8, _ = create_course("BT201", "Bioinformatics & Genomic Algorithms", "Sequence alignment, dynamic programming in genomics, and molecular phylogenetic trees.", admin_id)

    # 3. Examiners across departments
    print("[2/6] Registering Faculty Examiners...")
    ex1_id, _ = register_examiner("dr_sharma", "sharma@emp.edu", "Pass@123", "FAC202601", "Dr. Rajesh Sharma", "Computer Science", "Professor", "+91 9811122233")
    ex2_id, _ = register_examiner("dr_priya", "priya@emp.edu", "Pass@123", "FAC202602", "Dr. Priya Raman", "Information Technology", "Associate Professor", "+91 9822233344")
    ex3_id, _ = register_examiner("prof_kapoor", "kapoor@emp.edu", "Pass@123", "FAC202603", "Prof. Amit Kapoor", "Software Engineering", "Assistant Professor", "+91 9833344455")
    ex4_id, _ = register_examiner("dr_gupta", "gupta@emp.edu", "Pass@123", "FAC202604", "Dr. Neha Gupta", "Electrical & AI", "Associate Professor", "+91 9844455566")
    ex5_id, _ = register_examiner("dr_bose", "bose@emp.edu", "Pass@123", "FAC202605", "Dr. Subhash Bose", "Mechanical Engineering", "Professor", "+91 9855566677")

    # Approve examiners (leave prof_kapoor pending review for demo verification)
    update_examiner_status(ex1_id, 'approved', admin_id)
    update_examiner_status(ex2_id, 'approved', admin_id)
    update_examiner_status(ex4_id, 'approved', admin_id)
    update_examiner_status(ex5_id, 'approved', admin_id)

    # 4. Students across different courses/programs
    print("[3/6] Registering Diverse Student Cohorts...")
    # Computer Science & Software Engineering
    s1_id, _ = register_student("student_aryan", "aryan@emp.edu", "Pass@123", "STU2026001", "Aryan Sharma", "Computer Science", "B.Tech CSE (6th Sem)", "+91 9900112233")
    s2_id, _ = register_student("student_rohan", "rohan@emp.edu", "Pass@123", "STU2026002", "Rohan Verma", "Computer Science", "B.Tech CSE (6th Sem)", "+91 9900223344")
    s3_id, _ = register_student("student_ananya", "ananya@emp.edu", "Pass@123", "STU2026003", "Ananya Iyer", "Information Technology", "B.Tech IT (4th Sem)", "+91 9900334455")
    s4_id, _ = register_student("student_vikram", "vikram@emp.edu", "Pass@123", "STU2026004", "Vikram Singh", "Software Engineering", "M.Tech SE (2nd Sem)", "+91 9900445566")
    s5_id, _ = register_student("student_diya", "diya@emp.edu", "Pass@123", "STU2026005", "Diya Patel", "Computer Science", "B.Tech CSE (6th Sem)", "+91 9900556677")

    # Electrical, Electronics & Mechanical
    s6_id, _ = register_student("student_kabir", "kabir@emp.edu", "Pass@123", "STU2026006", "Kabir Mehta", "Electrical Engineering", "B.Tech EEE (5th Sem)", "+91 9900667788")
    s7_id, _ = register_student("student_pooja", "pooja@emp.edu", "Pass@123", "STU2026007", "Pooja Hegde", "Electronics & Communication", "B.Tech ECE (6th Sem)", "+91 9900778899")
    s8_id, _ = register_student("student_arjun", "arjun@emp.edu", "Pass@123", "STU2026008", "Arjun Singhania", "Mechanical Engineering", "B.Tech Mech (7th Sem)", "+91 9900889900")

    # Data Science, AI & Biotechnology
    s9_id, _ = register_student("student_meera", "meera@emp.edu", "Pass@123", "STU2026009", "Meera Nambiar", "Data Science & Analytics", "B.Sc Data Science (3rd Sem)", "+91 9900990011")
    s10_id, _ = register_student("student_rahul", "rahul@emp.edu", "Pass@123", "STU2026010", "Rahul Deshmukh", "Artificial Intelligence", "M.Tech AI (2nd Sem)", "+91 9901112233")
    s11_id, _ = register_student("student_sneha", "sneha@emp.edu", "Pass@123", "STU2026011", "Sneha Kulkarni", "Biotechnology", "B.Tech Biotech (4th Sem)", "+91 9902223344")
    s12_id, _ = register_student("student_tanvi", "tanvi@emp.edu", "Pass@123", "STU2026012", "Tanvi Rao", "Civil & Environmental", "B.Tech Civil (5th Sem)", "+91 9903334455")

    # 5. Examinations and Rubrics
    print("[4/6] Configuring Multi-Department Examinations and Rubrics...")
    now = datetime.now()
    d_yesterday = (now - timedelta(days=2)).strftime("%Y-%m-%d %H:%M:%S")
    d_tomorrow = (now + timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
    d_next_month = (now + timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")

    # Timelines: past dates for completed exams, active dates for current exams
    d_past_14 = (now - timedelta(days=14)).strftime("%Y-%m-%d %H:%M:%S")
    d_past_10 = (now - timedelta(days=10)).strftime("%Y-%m-%d %H:%M:%S")
    d_past_3 = (now - timedelta(days=3)).strftime("%Y-%m-%d %H:%M:%S")

    # Exam 1: CS101 Booking Open
    exam1_id, _ = create_examination(
        course_id=c1,
        title="CS101 Midterm Practical Viva",
        exam_type="Midterm Viva",
        duration_minutes=20,
        max_marks=50.0,
        slot_creation_start=d_yesterday,
        slot_creation_end=d_tomorrow,
        booking_start=d_yesterday,
        booking_end=d_tomorrow,
        status="booking_open",
        admin_user_id=admin_id
    )
    add_rubric_criterion(exam1_id, "Data Structure Implementation", "Correctness of linked list/tree pointer manipulation and edge conditions", 20.0, 40.0, 1, admin_id)
    add_rubric_criterion(exam1_id, "Algorithmic Complexity Defense", "Justification of Big-O time and auxiliary space consumption", 15.0, 30.0, 2, admin_id)
    add_rubric_criterion(exam1_id, "Viva Q&A & Code Walkthrough", "Clarity of verbal articulation and technical answers to faculty inquiries", 15.0, 30.0, 3, admin_id)
    assign_examiner_to_exam(exam1_id, ex1_id, admin_id)
    assign_examiner_to_exam(exam1_id, ex2_id, admin_id)

    # Exam 2: CS201 Completed & Published (Historical - concluded in the past)
    exam2_id, _ = create_examination(
        course_id=c2,
        title="CS201 End-Semester Project Evaluation",
        exam_type="Project Evaluation",
        duration_minutes=30,
        max_marks=100.0,
        slot_creation_start=d_past_14,
        slot_creation_end=d_past_10,
        booking_start=d_past_10,
        booking_end=d_past_3,
        status="completed",
        admin_user_id=admin_id
    )
    add_rubric_criterion(exam2_id, "Relational Schema & 3NF Normalization", "E-R modeling quality and decomposition integrity", 25.0, 25.0, 1, admin_id)
    add_rubric_criterion(exam2_id, "Complex Query Design & Indexing", "Use of JOINs, aggregation, subqueries, and execution plans", 35.0, 35.0, 2, admin_id)
    add_rubric_criterion(exam2_id, "Application Integration & ACID Testing", "Driver connection, transaction rollback handling, and sanitization", 20.0, 20.0, 3, admin_id)
    add_rubric_criterion(exam2_id, "Presentation & Viva Defense", "Quality of slides, live demo, and answers to evaluator queries", 20.0, 20.0, 4, admin_id)
    assign_examiner_to_exam(exam2_id, ex2_id, admin_id)

    # Exam 3: EE102 Booking Open (Electrical Engineering)
    exam3_id, _ = create_examination(
        course_id=c5,
        title="EE102 Digital Electronics Circuit Defense",
        exam_type="Oral Practical",
        duration_minutes=25,
        max_marks=60.0,
        slot_creation_start=d_yesterday,
        slot_creation_end=d_tomorrow,
        booking_start=d_yesterday,
        booking_end=d_tomorrow,
        status="booking_open",
        admin_user_id=admin_id
    )
    add_rubric_criterion(exam3_id, "Circuit Schematic & Karnaugh Mapping", "Boolean simplification and timing hazard mitigation", 20.0, 35.0, 1, admin_id)
    add_rubric_criterion(exam3_id, "Breadboard Hardware / Simulation", "Oscilloscope waveform verification and clock pulse generation", 25.0, 40.0, 2, admin_id)
    add_rubric_criterion(exam3_id, "Component Selection & Troubleshooting", "Logic IC specifications and propagation delay explanation", 15.0, 25.0, 3, admin_id)
    assign_examiner_to_exam(exam3_id, ex4_id, admin_id)

    # Exam 4: DS205 Booking Open (Data Science)
    exam4_id, _ = create_examination(
        course_id=c6,
        title="DS205 Statistical Modeling & Inference Viva",
        exam_type="Midterm Viva",
        duration_minutes=30,
        max_marks=75.0,
        slot_creation_start=d_yesterday,
        slot_creation_end=d_tomorrow,
        booking_start=d_yesterday,
        booking_end=d_tomorrow,
        status="booking_open",
        admin_user_id=admin_id
    )
    add_rubric_criterion(exam4_id, "Regression & Hypothesis Formulation", "p-value interpretation, ANOVA, and residual diagnostics", 30.0, 40.0, 1, admin_id)
    add_rubric_criterion(exam4_id, "Python/R Statistical Pipeline", "Clean data ingestion, feature scaling, and bootstrap tests", 25.0, 35.0, 2, admin_id)
    add_rubric_criterion(exam4_id, "Oral Questioning & Defense", "Generalization bounds, overfitting avoidance, and metrics", 20.0, 25.0, 3, admin_id)
    assign_examiner_to_exam(exam4_id, ex1_id, admin_id)

    # Exam 5: ME302 Slot Creation Phase (Mechanical Engineering)
    exam5_id, _ = create_examination(
        course_id=c7,
        title="ME302 Thermodynamic Cycle Analysis",
        exam_type="Oral Practical",
        duration_minutes=35,
        max_marks=100.0,
        slot_creation_start=d_yesterday,
        slot_creation_end=d_tomorrow,
        booking_start=d_tomorrow,
        booking_end=d_next_month,
        status="slot_creation",
        admin_user_id=admin_id
    )
    add_rubric_criterion(exam5_id, "Rankine & Brayton Cycle Calculations", "Thermal efficiency and heat rate derivation", 50.0, 50.0, 1, admin_id)
    add_rubric_criterion(exam5_id, "Experimental Rig Evaluation", "Boiler pressure curves and combustion losses", 50.0, 50.0, 2, admin_id)
    assign_examiner_to_exam(exam5_id, ex5_id, admin_id)

    # 6. Slots, Bookings, and Evaluations
    print("[5/6] Scheduling Slots and Bookings Across Disciplines...")
    slot1_date = (now + timedelta(days=2)).strftime("%Y-%m-%d")
    slot2_date = (now + timedelta(days=3)).strftime("%Y-%m-%d")
    slot3_date = (now + timedelta(days=4)).strftime("%Y-%m-%d")
    past_date = (now - timedelta(days=1)).strftime("%Y-%m-%d")

    # Exam 1 Slots (CS101)
    s1_slot_id, _ = create_slot(exam1_id, ex1_id, slot1_date, "09:30", "11:30", "Lab 301, Turing Block", 3, bypass_window_check=True)
    s2_slot_id, _ = create_slot(exam1_id, ex1_id, slot1_date, "13:00", "15:00", "Lab 301, Turing Block", 2, bypass_window_check=True)
    s3_slot_id, _ = create_slot(exam1_id, ex2_id, slot2_date, "10:00", "12:00", "Virtual Hall A (Meet Link)", 3, bypass_window_check=True)

    # Bookings for Exam 1
    book_examination_slot(s1_id, exam1_id, s1_slot_id, "Student self-booking")
    book_examination_slot(s2_id, exam1_id, s1_slot_id, "Student self-booking")
    book_examination_slot(s3_id, exam1_id, s3_slot_id, "Student self-booking")
    book_examination_slot(s4_id, exam1_id, s3_slot_id, "Student self-booking")

    # Exam 3 Slots (EE102 - Electrical)
    ee_slot1_id, _ = create_slot(exam3_id, ex4_id, slot2_date, "09:00", "11:00", "Digital Circuits Lab 104", 3, bypass_window_check=True)
    ee_slot2_id, _ = create_slot(exam3_id, ex4_id, slot2_date, "11:30", "13:30", "Digital Circuits Lab 104", 2, bypass_window_check=True)
    book_examination_slot(s6_id, exam3_id, ee_slot1_id, "Student self-booking")
    book_examination_slot(s7_id, exam3_id, ee_slot1_id, "Student self-booking")

    # Exam 4 Slots (DS205 - Data Science)
    ds_slot1_id, _ = create_slot(exam4_id, ex1_id, slot3_date, "14:00", "16:00", "Analytics Studio Lab B", 3, bypass_window_check=True)
    book_examination_slot(s9_id, exam4_id, ds_slot1_id, "Student self-booking")
    book_examination_slot(s10_id, exam4_id, ds_slot1_id, "Student self-booking")

    # Exam 2 Slots (CS201 - Conducted and Evaluated in the past)
    slot_past_id, _ = create_slot(exam2_id, ex2_id, past_date, "10:00", "12:00", "Database Systems Lab 202", 2, bypass_window_check=True)
    b_past1_id, _ = book_examination_slot(s1_id, exam2_id, slot_past_id, "Pre-scheduled booking", bypass_window_check=True)
    b_past2_id, _ = book_examination_slot(s5_id, exam2_id, slot_past_id, "Pre-scheduled booking", bypass_window_check=True)

    print("[6/6] Submitting Rubric Evaluations and Publishing Results...")
    r_list = db.execute("SELECT id FROM examination_rubrics WHERE examination_id = ? ORDER BY display_order ASC", (exam2_id,)).fetchall()
    r_ids = [r['id'] for r in r_list]

    # Evaluate student_aryan on Exam 2
    marks_s1 = {str(r_ids[0]): 24.0, str(r_ids[1]): 33.5, str(r_ids[2]): 19.0, str(r_ids[3]): 19.5}
    rem_s1 = {str(r_ids[0]): "Flawless BCNF normalization proof", str(r_ids[1]): "Indexed B-Tree join optimization was outstanding"}
    save_or_submit_evaluation(b_past1_id, ex2_id, marks_s1, rem_s1, "Exemplary understanding of storage engine internals and concurrency guarantees.", is_submit=True)

    # Evaluate student_diya on Exam 2
    marks_s5 = {str(r_ids[0]): 21.0, str(r_ids[1]): 30.0, str(r_ids[2]): 18.0, str(r_ids[3]): 17.0}
    rem_s5 = {str(r_ids[0]): "Good 3NF breakdown, minor redundancy in table 4"}
    save_or_submit_evaluation(b_past2_id, ex2_id, marks_s5, rem_s5, "Solid implementation of transactions and RESTful DB API endpoints.", is_submit=True)

    # Publish results for Exam 2
    publish_exam_results(exam2_id, admin_id, "Official End-Semester Project Grades Certified by Department Examination Cell")

    print("\n" + "=" * 60)
    print("  Seed Data Population Completed Successfully!")
    print("=" * 60)
    print("Academic Cohort Summary:")
    print("  Courses:    8 courses across CSE, IT, EE, DS, ME, Biotech")
    print("  Examiners:  5 faculty members (4 approved, 1 pending)")
    print("  Students:   12 enrolled students across diverse programs")
    print("\nPre-configured Demonstration Accounts:")
    print("  Administrator:  admin          / Admin@123")
    print("  Examiner (CS):  dr_sharma      / Pass@123")
    print("  Examiner (IT):  dr_priya       / Pass@123")
    print("  Examiner (EE):  dr_gupta       / Pass@123")
    print("  Examiner (ME):  dr_bose        / Pass@123")
    print("  Examiner (Pend):prof_kapoor    / Pass@123 (Approval workflow demo)")
    print("  Student (CS):   student_aryan  / Pass@123 (Active bookings + Published result)")
    print("  Student (CS):   student_rohan  / Pass@123")
    print("  Student (IT):   student_ananya / Pass@123")
    print("  Student (SE):   student_vikram / Pass@123")
    print("  Student (EE):   student_kabir  / Pass@123 (Booked in EE102)")
    print("  Student (ECE):  student_pooja  / Pass@123 (Booked in EE102)")
    print("  Student (DS):   student_meera  / Pass@123 (Booked in DS205)")
    print("  Student (AI):   student_rahul  / Pass@123 (Booked in DS205)")
    print("  Student (Mech): student_arjun  / Pass@123")
    print("  Student (Bio):  student_sneha  / Pass@123")
    print("  Student (Civil):student_tanvi  / Pass@123")
    print("=" * 60)

if __name__ == '__main__':
    seed()
