"""Realistic sample semester data generator for first-time ScholarFlow users."""

from __future__ import annotations

import sqlite3
from datetime import date, datetime, timedelta, timezone


def seed_sample_data(conn: sqlite3.Connection, today: date | None = None, force: bool = False) -> bool:
    """Populate realistic courses, assessments, tasks, sessions, habits, and schedule blocks.

    Returns True if data was seeded, False if skipped (already seeded/populated).
    """
    ref_day = today or date.today()
    now_iso = datetime.now(timezone.utc).isoformat()

    if not force:
        flag = conn.execute("SELECT value FROM settings WHERE key = 'seeded'").fetchone()
        course_cnt = conn.execute("SELECT COUNT(*) AS cnt FROM courses").fetchone()["cnt"]
        task_cnt = conn.execute("SELECT COUNT(*) AS cnt FROM tasks").fetchone()["cnt"]
        if (flag and flag["value"] == "1") or course_cnt > 0 or task_cnt > 0:
            return False
    else:
        clear_all_data(conn)

    courses_seed = [
        ("CS 201", "Data Structures & Algorithms", "#4f46e5", 4.0, 92.0, "Prof. Elena Vance"),
        ("MATH 240", "Linear Algebra", "#0ea5e9", 3.0, 90.0, "Dr. Marcus Lin"),
        ("PHYS 180", "Mechanics & Waves", "#10b981", 4.0, 88.0, "Prof. Priya Nair"),
        ("HIST 115", "Modern World History", "#f59e0b", 3.0, 90.0, "Dr. Julian Brooks"),
    ]
    course_ids: dict[str, int] = {}
    for code, name, color, credits, target, instructor in courses_seed:
        cur = conn.execute(
            "INSERT INTO courses (code, name, color, credits, target_grade, instructor, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (code, name, color, credits, target, instructor, now_iso),
        )
        course_ids[code] = int(cur.lastrowid)

    # Assessments
    assessments_seed = [
        ("CS 201", "Midterm Exam", "Exam", 89, 100, 25, (ref_day - timedelta(days=14)).isoformat()),
        ("CS 201", "Lab 1: Recursion & Trees", "Lab", 47, 50, 15, (ref_day - timedelta(days=20)).isoformat()),
        ("CS 201", "Graph Traversal Assignment", "Assignment", 95, 100, 15, (ref_day - timedelta(days=5)).isoformat()),
        ("MATH 240", "Quiz 1: Vector Spaces", "Quiz", 18, 20, 10, (ref_day - timedelta(days=18)).isoformat()),
        ("MATH 240", "Problem Set 1-3", "Assignment", 84, 100, 20, (ref_day - timedelta(days=8)).isoformat()),
        ("MATH 240", "Midterm 1", "Exam", 82, 100, 25, (ref_day - timedelta(days=3)).isoformat()),
        ("PHYS 180", "Kinematics Lab Report", "Lab", 44, 50, 15, (ref_day - timedelta(days=12)).isoformat()),
        ("PHYS 180", "Midterm Exam", "Exam", 79, 100, 30, (ref_day - timedelta(days=6)).isoformat()),
        ("HIST 115", "Primary Source Essay", "Assignment", 93, 100, 25, (ref_day - timedelta(days=9)).isoformat()),
        ("HIST 115", "Seminar Participation", "Quiz", 19, 20, 15, (ref_day - timedelta(days=2)).isoformat()),
    ]
    for code, title, cat, score, max_score, weight, rec_date in assessments_seed:
        conn.execute(
            "INSERT INTO assessments (course_id, title, category, score, max_score, weight, recorded_date) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (course_ids[code], title, cat, score, max_score, weight, rec_date),
        )

    # Tasks & Assignments
    tasks_seed = [
        (
            "Implement Dijkstra shortest-path lab",
            course_ids["CS 201"],
            "Assignment",
            "high",
            ref_day.isoformat(),
            75,
            "Finish priority queue edge cases and run benchmark tests.",
            0,
            None,
        ),
        (
            "Eigenvalues & diagonalization practice set",
            course_ids["MATH 240"],
            "Assignment",
            "high",
            (ref_day + timedelta(days=1)).isoformat(),
            60,
            "Focus on problems 4 through 9 before tomorrow's recitation.",
            0,
            None,
        ),
        (
            "Oscillations & wave interference pre-lab",
            course_ids["PHYS 180"],
            "Reading",
            "medium",
            (ref_day + timedelta(days=2)).isoformat(),
            40,
            "Read chapter 14 summary and derive standing wave equation.",
            0,
            None,
        ),
        (
            "Outline Comparative Industrialization Paper",
            course_ids["HIST 115"],
            "Project",
            "medium",
            (ref_day + timedelta(days=4)).isoformat(),
            50,
            "Gather 3 peer-reviewed primary sources.",
            0,
            None,
        ),
        (
            "CS 201 Dynamic Programming Quiz Prep",
            course_ids["CS 201"],
            "Exam",
            "high",
            (ref_day + timedelta(days=6)).isoformat(),
            90,
            "Review memoization vs tabulation patterns.",
            0,
            None,
        ),
        (
            "Submit weekly physics homework #5",
            course_ids["PHYS 180"],
            "Assignment",
            "medium",
            (ref_day - timedelta(days=1)).isoformat(),
            45,
            "Double-check unit conversions on question 6.",
            1,
            now_iso,
        ),
        (
            "Organize lecture notes for Week 7",
            None,
            "Personal",
            "low",
            (ref_day - timedelta(days=2)).isoformat(),
            25,
            "Sync PDF annotations into study folder.",
            1,
            now_iso,
        ),
    ]
    task_ids: list[int] = []
    for title, cid, ttype, prio, due, est, notes, comp, comp_at in tasks_seed:
        cur = conn.execute(
            "INSERT INTO tasks (title, course_id, task_type, priority, due_date, "
            "estimated_minutes, notes, completed, completed_at, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (title, cid, ttype, prio, due, est, notes, comp, comp_at, now_iso),
        )
        task_ids.append(int(cur.lastrowid))

    # Study sessions over the last 7 days
    sessions_seed = [
        (course_ids["CS 201"], None, 50, (ref_day - timedelta(days=6)).isoformat(), "focus", "Balanced BST rotations"),
        (course_ids["MATH 240"], None, 45, (ref_day - timedelta(days=6)).isoformat(), "focus", "Matrix rank proofs"),
        (course_ids["PHYS 180"], None, 60, (ref_day - timedelta(days=5)).isoformat(), "review", "Midterm error review"),
        (course_ids["HIST 115"], None, 40, (ref_day - timedelta(days=4)).isoformat(), "focus", "Annotated bibliography"),
        (course_ids["CS 201"], None, 75, (ref_day - timedelta(days=3)).isoformat(), "focus", "Heaps & priority queues"),
        (course_ids["MATH 240"], None, 55, (ref_day - timedelta(days=2)).isoformat(), "focus", "Determinant properties"),
        (course_ids["PHYS 180"], None, 50, (ref_day - timedelta(days=1)).isoformat(), "focus", "Harmonic motion problems"),
        (course_ids["CS 201"], None, 45, (ref_day - timedelta(days=1)).isoformat(), "focus", "Graph BFS/DFS drills"),
        (course_ids["CS 201"], task_ids[0], 50, ref_day.isoformat(), "focus", "Started Dijkstra implementation"),
    ]
    for cid, tid, mins, sdate, mode, notes in sessions_seed:
        conn.execute(
            "INSERT INTO study_sessions (course_id, task_id, duration_minutes, session_date, mode, notes, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (cid, tid, mins, sdate, mode, notes, now_iso),
        )

    # Habits + logs over past 7 days
    habits_seed = [
        ("Review lecture notes same day", "Study", 5, [0, 1, 2, 4, 5]),
        ("Phone in another room during focus", "Study", 6, [0, 1, 2, 3, 5, 6]),
        ("Solve 3 practice problems daily", "Study", 5, [1, 2, 4, 5]),
        ("7.5+ hours sleep & wind-down", "Wellness", 6, [0, 2, 3, 4, 5]),
        ("Plan tomorrow's top 3 tasks", "Organization", 5, [0, 1, 3, 5, 6]),
    ]
    for title, category, target_days, offsets in habits_seed:
        cur = conn.execute(
            "INSERT INTO habits (title, category, target_days_per_week, created_at) VALUES (?, ?, ?, ?)",
            (title, category, target_days, now_iso),
        )
        hid = int(cur.lastrowid)
        for off in offsets:
            log_date = (ref_day - timedelta(days=off)).isoformat()
            conn.execute(
                "INSERT OR IGNORE INTO habit_logs (habit_id, log_date) VALUES (?, ?)",
                (hid, log_date),
            )

    # Weekly schedule blocks
    schedule_seed = [
        ("CS 201 Lecture", course_ids["CS 201"], 0, "09:30", "10:45", "Class", "Gates Hall 210"),
        ("MATH 240 Lecture", course_ids["MATH 240"], 0, "13:00", "14:15", "Class", "Euler 104"),
        ("Deep Focus: Problem Sets", None, 0, "16:00", "17:30", "Study", "Main Library 3F"),
        ("PHYS 180 Lecture", course_ids["PHYS 180"], 1, "10:00", "11:15", "Class", "Newton Hall 112"),
        ("HIST 115 Seminar", course_ids["HIST 115"], 1, "14:00", "15:15", "Class", "Humanities 308"),
        ("CS 201 Lecture", course_ids["CS 201"], 2, "09:30", "10:45", "Class", "Gates Hall 210"),
        ("PHYS 180 Lab", course_ids["PHYS 180"], 2, "14:00", "16:00", "Lab", "Physics Wing B12"),
        ("MATH 240 Recitation", course_ids["MATH 240"], 3, "11:00", "12:00", "Lab", "Euler 202"),
        ("HIST 115 Seminar", course_ids["HIST 115"], 3, "14:00", "15:15", "Class", "Humanities 308"),
        ("CS 201 Coding Lab", course_ids["CS 201"], 4, "10:30", "12:00", "Lab", "Gates Lab 105"),
        ("Weekly Review & Planning", None, 6, "17:00", "18:00", "Study", "Desk"),
    ]
    for title, cid, dow, start_t, end_t, btype, loc in schedule_seed:
        conn.execute(
            "INSERT INTO schedule_blocks (title, course_id, day_of_week, start_time, end_time, block_type, location) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (title, cid, dow, start_t, end_t, btype, loc),
        )

    conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('seeded', '1')")
    return True


def clear_all_data(conn: sqlite3.Connection) -> None:
    """Remove all user records while preserving preferences and marking seeded=1 so sample won't auto-reappear."""
    conn.execute("DELETE FROM habit_logs")
    conn.execute("DELETE FROM habits")
    conn.execute("DELETE FROM study_sessions")
    conn.execute("DELETE FROM schedule_blocks")
    conn.execute("DELETE FROM tasks")
    conn.execute("DELETE FROM assessments")
    conn.execute("DELETE FROM courses")
    conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('seeded', '1')")
