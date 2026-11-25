"""Performance analytics, grade projections, streak calculation, and dashboard aggregation."""

from __future__ import annotations

import sqlite3
from datetime import date, timedelta
from typing import Any


def percentage_to_letter_and_gpa(pct: float) -> tuple[str, float]:
    """Convert a percentage grade (0-100+) into letter grade and 4.0 GPA points."""
    if pct >= 93.0:
        return ("A", 4.0)
    if pct >= 90.0:
        return ("A-", 3.7)
    if pct >= 87.0:
        return ("B+", 3.3)
    if pct >= 83.0:
        return ("B", 3.0)
    if pct >= 80.0:
        return ("B-", 2.7)
    if pct >= 77.0:
        return ("C+", 2.3)
    if pct >= 73.0:
        return ("C", 2.0)
    if pct >= 70.0:
        return ("C-", 1.7)
    if pct >= 67.0:
        return ("D+", 1.3)
    if pct >= 60.0:
        return ("D", 1.0)
    return ("F", 0.0)


def compute_course_metrics(
    conn: sqlite3.Connection,
    today: date | None = None,
) -> list[dict[str, Any]]:
    """Compute weighted grades, remaining weight, target requirements, and study totals per course."""
    ref_day = today or date.today()
    courses = conn.execute(
        "SELECT id, code, name, color, credits, target_grade, instructor, created_at "
        "FROM courses ORDER BY code COLLATE NOCASE ASC"
    ).fetchall()

    assessments_rows = conn.execute(
        "SELECT id, course_id, title, category, score, max_score, weight, recorded_date "
        "FROM assessments ORDER BY recorded_date DESC, id DESC"
    ).fetchall()

    task_counts_rows = conn.execute(
        "SELECT course_id, "
        "SUM(CASE WHEN completed = 0 THEN 1 ELSE 0 END) AS open_tasks, "
        "SUM(CASE WHEN completed = 1 THEN 1 ELSE 0 END) AS completed_tasks "
        "FROM tasks WHERE course_id IS NOT NULL GROUP BY course_id"
    ).fetchall()

    session_totals_rows = conn.execute(
        "SELECT course_id, COALESCE(SUM(duration_minutes), 0) AS total_minutes "
        "FROM study_sessions WHERE course_id IS NOT NULL GROUP BY course_id"
    ).fetchall()

    assessments_by_course: dict[int, list[dict[str, Any]]] = {}
    for row in assessments_rows:
        pct = round((row["score"] / row["max_score"]) * 100.0, 1)
        item = {
            "id": row["id"],
            "course_id": row["course_id"],
            "title": row["title"],
            "category": row["category"],
            "score": row["score"],
            "max_score": row["max_score"],
            "percentage": pct,
            "weight": row["weight"],
            "recorded_date": row["recorded_date"],
        }
        assessments_by_course.setdefault(row["course_id"], []).append(item)

    task_counts = {
        r["course_id"]: {
            "open_tasks": r["open_tasks"] or 0,
            "completed_tasks": r["completed_tasks"] or 0,
        }
        for r in task_counts_rows
    }
    session_totals = {r["course_id"]: r["total_minutes"] or 0 for r in session_totals_rows}

    result: list[dict[str, Any]] = []
    for course in courses:
        cid = course["id"]
        c_assessments = assessments_by_course.get(cid, [])
        completed_weight = round(sum(a["weight"] for a in c_assessments), 1)
        remaining_weight = round(max(0.0, 100.0 - completed_weight), 1)

        current_grade: float | None = None
        letter_grade: str | None = None
        gpa_points: float | None = None
        needed_for_target: float | None = None
        status = "no_grades"

        if completed_weight > 0:
            weighted_earned = sum(
                (a["score"] / a["max_score"]) * 100.0 * a["weight"] for a in c_assessments
            )
            current_grade = round(weighted_earned / completed_weight, 1)
            letter_grade, gpa_points = percentage_to_letter_and_gpa(current_grade)

            if remaining_weight > 0:
                needed_raw = (course["target_grade"] * 100.0 - weighted_earned) / remaining_weight
                needed_for_target = round(needed_raw, 1)

            if current_grade >= course["target_grade"]:
                status = "on_track"
            elif current_grade >= course["target_grade"] - 5.0:
                status = "close"
            else:
                status = "needs_focus"

        counts = task_counts.get(cid, {"open_tasks": 0, "completed_tasks": 0})
        result.append(
            {
                "id": cid,
                "code": course["code"],
                "name": course["name"],
                "color": course["color"],
                "credits": course["credits"],
                "target_grade": course["target_grade"],
                "instructor": course["instructor"],
                "created_at": course["created_at"],
                "assessments": c_assessments,
                "completed_weight": completed_weight,
                "remaining_weight": remaining_weight,
                "current_grade": current_grade,
                "letter_grade": letter_grade,
                "gpa_points": gpa_points,
                "needed_for_target": needed_for_target,
                "status": status,
                "open_tasks": counts["open_tasks"],
                "completed_tasks": counts["completed_tasks"],
                "study_minutes_total": session_totals.get(cid, 0),
                "as_of": ref_day.isoformat(),
            }
        )
    return result


def compute_streak(conn: sqlite3.Connection, today: date | None = None) -> dict[str, Any]:
    """Calculate current active study/habit streak ending today or yesterday."""
    ref_day = today or date.today()
    study_days_rows = conn.execute(
        "SELECT session_date, SUM(duration_minutes) AS mins "
        "FROM study_sessions GROUP BY session_date HAVING mins >= 15"
    ).fetchall()
    habit_days_rows = conn.execute(
        "SELECT DISTINCT log_date FROM habit_logs"
    ).fetchall()

    active_dates: set[str] = {r["session_date"] for r in study_days_rows}
    active_dates.update(r["log_date"] for r in habit_days_rows)

    today_iso = ref_day.isoformat()
    active_today = today_iso in active_dates

    cursor = ref_day if active_today else ref_day - timedelta(days=1)
    streak = 0
    while cursor.isoformat() in active_dates:
        streak += 1
        cursor -= timedelta(days=1)

    return {
        "days": streak,
        "active_today": active_today,
    }


def compute_habits_with_grid(
    conn: sqlite3.Connection,
    today: date | None = None,
) -> dict[str, Any]:
    """Return habits along with their 7-day rolling completion status and streak."""
    ref_day = today or date.today()
    days = [ref_day - timedelta(days=offset) for offset in range(6, -1, -1)]
    day_isos = [d.isoformat() for d in days]
    day_headers = [
        {
            "date": d.isoformat(),
            "label": d.strftime("%a"),
            "day_num": d.day,
            "is_today": d == ref_day,
        }
        for d in days
    ]

    habits = conn.execute(
        "SELECT id, title, category, target_days_per_week, created_at "
        "FROM habits ORDER BY id ASC"
    ).fetchall()
    all_logs = conn.execute(
        "SELECT habit_id, log_date FROM habit_logs ORDER BY log_date DESC"
    ).fetchall()

    logs_by_habit: dict[int, set[str]] = {}
    for row in all_logs:
        logs_by_habit.setdefault(row["habit_id"], set()).add(row["log_date"])

    items: list[dict[str, Any]] = []
    for habit in habits:
        hid = habit["id"]
        h_dates = logs_by_habit.get(hid, set())
        week_checks = [d_iso in h_dates for d_iso in day_isos]
        week_count = sum(1 for checked in week_checks if checked)

        # Per-habit current streak ending today or yesterday
        cursor = ref_day if ref_day.isoformat() in h_dates else ref_day - timedelta(days=1)
        h_streak = 0
        while cursor.isoformat() in h_dates:
            h_streak += 1
            cursor -= timedelta(days=1)

        items.append(
            {
                "id": hid,
                "title": habit["title"],
                "category": habit["category"],
                "target_days_per_week": habit["target_days_per_week"],
                "created_at": habit["created_at"],
                "week_checks": week_checks,
                "week_count": week_count,
                "streak": h_streak,
                "completed_today": ref_day.isoformat() in h_dates,
            }
        )

    return {
        "days": day_headers,
        "habits": items,
    }


def build_dashboard_summary(
    conn: sqlite3.Connection,
    today: date | None = None,
) -> dict[str, Any]:
    """Aggregate KPIs, performance breakdown, 7-day charts, and urgent queue."""
    ref_day = today or date.today()
    today_iso = ref_day.isoformat()
    week_start_iso = (ref_day - timedelta(days=6)).isoformat()

    settings_rows = conn.execute("SELECT key, value FROM settings").fetchall()
    settings = {r["key"]: r["value"] for r in settings_rows}
    daily_goal = int(settings.get("daily_study_goal_minutes", "120"))

    courses = compute_course_metrics(conn, ref_day)
    course_map = {c["id"]: c for c in courses}

    # GPA & average percentage across graded courses
    graded = [c for c in courses if c["current_grade"] is not None]
    estimated_gpa: float | None = None
    weighted_avg_grade: float | None = None
    if graded:
        total_credits = sum(c["credits"] for c in graded)
        if total_credits > 0:
            estimated_gpa = round(
                sum((c["gpa_points"] or 0.0) * c["credits"] for c in graded) / total_credits,
                2,
            )
            weighted_avg_grade = round(
                sum((c["current_grade"] or 0.0) * c["credits"] for c in graded) / total_credits,
                1,
            )

    # Tasks metrics
    task_rows = conn.execute(
        "SELECT t.id, t.title, t.course_id, t.task_type, t.priority, t.due_date, "
        "t.estimated_minutes, t.notes, t.completed, t.completed_at, t.created_at "
        "FROM tasks t ORDER BY t.completed ASC, "
        "CASE WHEN t.due_date IS NULL THEN 1 ELSE 0 END ASC, "
        "t.due_date ASC, "
        "CASE t.priority WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END ASC"
    ).fetchall()

    total_tasks = len(task_rows)
    completed_tasks = sum(1 for t in task_rows if t["completed"] == 1)
    open_tasks = total_tasks - completed_tasks
    overdue_tasks = sum(
        1 for t in task_rows
        if t["completed"] == 0 and t["due_date"] and t["due_date"] < today_iso
    )
    due_today_count = sum(
        1 for t in task_rows
        if t["completed"] == 0 and t["due_date"] == today_iso
    )
    due_soon_limit = (ref_day + timedelta(days=7)).isoformat()
    due_this_week_count = sum(
        1 for t in task_rows
        if t["completed"] == 0 and t["due_date"] and today_iso <= t["due_date"] <= due_soon_limit
    )

    priority_queue = []
    for t in task_rows:
        if t["completed"] == 1:
            continue
        course = course_map.get(t["course_id"])
        priority_queue.append(
            {
                "id": t["id"],
                "title": t["title"],
                "course_id": t["course_id"],
                "course_code": course["code"] if course else None,
                "course_color": course["color"] if course else "#64748b",
                "task_type": t["task_type"],
                "priority": t["priority"],
                "due_date": t["due_date"],
                "estimated_minutes": t["estimated_minutes"],
                "is_overdue": bool(t["due_date"] and t["due_date"] < today_iso),
            }
        )
        if len(priority_queue) >= 6:
            break

    # Study session metrics (last 7 days + today)
    session_rows = conn.execute(
        "SELECT id, course_id, duration_minutes, session_date "
        "FROM study_sessions WHERE session_date >= ? AND session_date <= ?",
        (week_start_iso, today_iso),
    ).fetchall()

    all_sessions_count = conn.execute("SELECT COUNT(*) AS cnt FROM study_sessions").fetchone()["cnt"]
    today_study_minutes = sum(
        s["duration_minutes"] for s in session_rows if s["session_date"] == today_iso
    )
    week_study_minutes = sum(s["duration_minutes"] for s in session_rows)

    # Daily 7-day stacked chart series
    day_buckets: dict[str, dict[int | None, int]] = {}
    for offset in range(6, -1, -1):
        d_iso = (ref_day - timedelta(days=offset)).isoformat()
        day_buckets[d_iso] = {}

    course_week_minutes: dict[int | None, int] = {}
    for s in session_rows:
        s_date = s["session_date"]
        cid = s["course_id"]
        mins = s["duration_minutes"]
        if s_date in day_buckets:
            day_buckets[s_date][cid] = day_buckets[s_date].get(cid, 0) + mins
        course_week_minutes[cid] = course_week_minutes.get(cid, 0) + mins

    study_chart_days = []
    for offset in range(6, -1, -1):
        d = ref_day - timedelta(days=offset)
        d_iso = d.isoformat()
        by_cid = day_buckets[d_iso]
        segments = []
        for cid, mins in by_cid.items():
            course = course_map.get(cid) if cid is not None else None
            segments.append(
                {
                    "course_id": cid,
                    "code": course["code"] if course else "General",
                    "color": course["color"] if course else "#94a3b8",
                    "minutes": mins,
                }
            )
        segments.sort(key=lambda seg: seg["minutes"], reverse=True)
        study_chart_days.append(
            {
                "date": d_iso,
                "label": d.strftime("%a"),
                "total_minutes": sum(by_cid.values()),
                "segments": segments,
            }
        )

    course_distribution = []
    for cid, mins in sorted(course_week_minutes.items(), key=lambda x: x[1], reverse=True):
        course = course_map.get(cid) if cid is not None else None
        course_distribution.append(
            {
                "course_id": cid,
                "code": course["code"] if course else "General",
                "name": course["name"] if course else "General Study",
                "color": course["color"] if course else "#94a3b8",
                "minutes": mins,
                "share_pct": round((mins / week_study_minutes) * 100.0, 1) if week_study_minutes else 0.0,
            }
        )

    # Habits summary
    habits_data = compute_habits_with_grid(conn, ref_day)
    habits_list = habits_data["habits"]
    habits_completed_today = sum(1 for h in habits_list if h["completed_today"])
    total_habits = len(habits_list)

    # Performance Score calculation (4 dimensions, 25 points each)
    # 1. Focus Rhythm
    focus_active = all_sessions_count > 0
    today_ratio = min(1.0, today_study_minutes / daily_goal) if daily_goal > 0 else 0.0
    week_avg_ratio = min(1.0, (week_study_minutes / 7.0) / daily_goal) if daily_goal > 0 else 0.0
    focus_points = round((0.5 * today_ratio + 0.5 * week_avg_ratio) * 25.0, 1)

    # 2. Task Execution
    tasks_active = total_tasks > 0
    if tasks_active:
        completion_ratio = completed_tasks / total_tasks
        overdue_penalty = min(8.0, overdue_tasks * 2.0)
        task_points = round(max(0.0, completion_ratio * 25.0 - overdue_penalty), 1)
    else:
        task_points = 0.0

    # 3. Habit Consistency
    habits_active = total_habits > 0
    if habits_active:
        target_sum = sum(h["target_days_per_week"] for h in habits_list)
        capped_done = sum(min(h["week_count"], h["target_days_per_week"]) for h in habits_list)
        habit_points = round((capped_done / target_sum) * 25.0, 1) if target_sum > 0 else 0.0
    else:
        habit_points = 0.0

    # 4. Academic Standing
    grades_active = weighted_avg_grade is not None
    grade_points = round(min(100.0, weighted_avg_grade) * 0.25, 1) if grades_active else 0.0

    breakdown = [
        {
            "key": "focus",
            "label": "Focus Rhythm",
            "score": focus_points,
            "max_score": 25.0,
            "active": focus_active,
            "detail": f"{today_study_minutes}/{daily_goal}m today · {week_study_minutes}m this week",
        },
        {
            "key": "tasks",
            "label": "Task Execution",
            "score": task_points,
            "max_score": 25.0,
            "active": tasks_active,
            "detail": f"{completed_tasks}/{total_tasks} completed · {overdue_tasks} overdue",
        },
        {
            "key": "habits",
            "label": "Habit Consistency",
            "score": habit_points,
            "max_score": 25.0,
            "active": habits_active,
            "detail": f"{habits_completed_today}/{total_habits} done today",
        },
        {
            "key": "grades",
            "label": "Academic Standing",
            "score": grade_points,
            "max_score": 25.0,
            "active": grades_active,
            "detail": (
                f"{weighted_avg_grade}% avg · {estimated_gpa} GPA"
                if grades_active
                else "Add graded assessments to track"
            ),
        },
    ]

    active_pillars = [b for b in breakdown if b["active"]]
    if active_pillars:
        raw_total = sum(b["score"] for b in active_pillars)
        max_possible = 25.0 * len(active_pillars)
        performance_score = int(round((raw_total / max_possible) * 100.0))
    else:
        performance_score = 0

    streak = compute_streak(conn, ref_day)

    # Smart actionable coaching tip based on current data
    coaching_tips: list[str] = []
    if overdue_tasks > 0:
        coaching_tips.append(
            f"Clear {overdue_tasks} overdue task{'s' if overdue_tasks > 1 else ''} first using a 25-minute focus sprint."
        )
    if today_study_minutes < daily_goal:
        remaining_mins = daily_goal - today_study_minutes
        coaching_tips.append(
            f"{remaining_mins} min left to reach today's {daily_goal}-min deep focus goal."
        )
    else:
        coaching_tips.append("Daily focus goal reached — great consistency today!")

    low_courses = [c for c in graded if c["status"] == "needs_focus"]
    if low_courses:
        worst = min(low_courses, key=lambda c: (c["current_grade"] or 0.0) - c["target_grade"])
        if worst["needed_for_target"] is not None:
            coaching_tips.append(
                f"{worst['code']} is at {worst['current_grade']}% (target {worst['target_grade']}%) — aim for {worst['needed_for_target']}% on remaining work."
            )

    # Today's schedule blocks
    today_weekday = ref_day.weekday()
    today_schedule_rows = conn.execute(
        "SELECT sb.id, sb.title, sb.course_id, sb.day_of_week, sb.start_time, sb.end_time, "
        "sb.block_type, sb.location "
        "FROM schedule_blocks sb WHERE sb.day_of_week = ? ORDER BY sb.start_time ASC",
        (today_weekday,),
    ).fetchall()
    today_schedule = []
    for blk in today_schedule_rows:
        course = course_map.get(blk["course_id"])
        today_schedule.append(
            {
                "id": blk["id"],
                "title": blk["title"],
                "course_id": blk["course_id"],
                "course_code": course["code"] if course else None,
                "course_color": course["color"] if course else "#64748b",
                "start_time": blk["start_time"],
                "end_time": blk["end_time"],
                "block_type": blk["block_type"],
                "location": blk["location"],
            }
        )

    return {
        "today": today_iso,
        "performance_score": performance_score,
        "performance_breakdown": breakdown,
        "streak": streak,
        "kpis": {
            "today_study_minutes": today_study_minutes,
            "daily_study_goal_minutes": daily_goal,
            "week_study_minutes": week_study_minutes,
            "open_tasks": open_tasks,
            "completed_tasks": completed_tasks,
            "overdue_tasks": overdue_tasks,
            "due_today_count": due_today_count,
            "due_this_week_count": due_this_week_count,
            "estimated_gpa": estimated_gpa,
            "weighted_avg_grade": weighted_avg_grade,
            "habits_completed_today": habits_completed_today,
            "total_habits": total_habits,
        },
        "priority_queue": priority_queue,
        "study_chart_days": study_chart_days,
        "course_distribution": course_distribution,
        "courses_snapshot": courses,
        "today_schedule": today_schedule,
        "coaching_tips": coaching_tips,
        "seeded": settings.get("seeded", "0") == "1",
    }
