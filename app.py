"""FastAPI application and REST API for ScholarFlow student performance tracker."""

from __future__ import annotations

import os
import sqlite3
from contextlib import asynccontextmanager
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Optional

import uvicorn
from fastapi import FastAPI, HTTPException, Query, status
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from analytics import build_dashboard_summary, compute_course_metrics, compute_habits_with_grid
from database import db_session, init_db
from models import (
    AssessmentCreate,
    CourseCreate,
    CourseUpdate,
    HabitCreate,
    HabitToggle,
    ScheduleBlockCreate,
    SettingsUpdate,
    StudySessionCreate,
    TaskCreate,
    TaskUpdate,
)
from seed import clear_all_data, seed_sample_data

STATIC_DIR = Path(__file__).resolve().parent / "static"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_course_exists(conn: sqlite3.Connection, course_id: Optional[int]) -> None:
    if course_id is None:
        return
    row = conn.execute("SELECT id FROM courses WHERE id = ?", (course_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Course not found")


def _ensure_task_exists(conn: sqlite3.Connection, task_id: Optional[int]) -> None:
    if task_id is None:
        return
    row = conn.execute("SELECT id FROM tasks WHERE id = ?", (task_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Task not found")


def _get_settings_dict(conn: sqlite3.Connection) -> dict[str, Any]:
    rows = conn.execute("SELECT key, value FROM settings").fetchall()
    raw = {r["key"]: r["value"] for r in rows}
    return {
        "student_name": raw.get("student_name", "Alex"),
        "semester_label": raw.get("semester_label", "Fall Semester"),
        "daily_study_goal_minutes": int(raw.get("daily_study_goal_minutes", "120")),
        "default_focus_minutes": int(raw.get("default_focus_minutes", "25")),
        "default_break_minutes": int(raw.get("default_break_minutes", "5")),
    }


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    if os.environ.get("SCHOLARFLOW_AUTO_SEED", "1") != "0":
        with db_session() as conn:
            seed_sample_data(conn)
    yield


app = FastAPI(title="ScholarFlow Student Tracker", version="1.0.0", lifespan=lifespan)

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/", include_in_schema=False)
def serve_index():
    index_path = STATIC_DIR / "index.html"
    if not index_path.exists():
        raise HTTPException(status_code=404, detail="Frontend assets missing")
    return FileResponse(index_path)


@app.get("/api/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/dashboard")
def get_dashboard() -> dict[str, Any]:
    with db_session() as conn:
        return build_dashboard_summary(conn)


# ---------------------------------------------------------------------------
# Courses & Assessments
# ---------------------------------------------------------------------------
@app.get("/api/courses")
def list_courses() -> list[dict[str, Any]]:
    with db_session() as conn:
        return compute_course_metrics(conn)


@app.post("/api/courses", status_code=status.HTTP_201_CREATED)
def create_course(payload: CourseCreate) -> dict[str, Any]:
    with db_session() as conn:
        cur = conn.execute(
            "INSERT INTO courses (code, name, color, credits, target_grade, instructor, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                payload.code,
                payload.name,
                payload.color,
                payload.credits,
                payload.target_grade,
                payload.instructor,
                _utc_now(),
            ),
        )
        cid = int(cur.lastrowid)
        courses = compute_course_metrics(conn)
        return next(c for c in courses if c["id"] == cid)


@app.patch("/api/courses/{course_id}")
def update_course(course_id: int, payload: CourseUpdate) -> dict[str, Any]:
    with db_session() as conn:
        existing = conn.execute("SELECT * FROM courses WHERE id = ?", (course_id,)).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="Course not found")

        updates: dict[str, Any] = {}
        if payload.code is not None:
            updates["code"] = payload.code.strip()
        if payload.name is not None:
            updates["name"] = payload.name.strip()
        if payload.color is not None:
            updates["color"] = payload.color
        if payload.credits is not None:
            updates["credits"] = payload.credits
        if payload.target_grade is not None:
            updates["target_grade"] = payload.target_grade
        if payload.instructor is not None:
            updates["instructor"] = payload.instructor.strip()

        if updates:
            set_clause = ", ".join(f"{col} = ?" for col in updates)
            conn.execute(
                f"UPDATE courses SET {set_clause} WHERE id = ?",
                (*updates.values(), course_id),
            )
        courses = compute_course_metrics(conn)
        return next(c for c in courses if c["id"] == course_id)


@app.delete("/api/courses/{course_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_course(course_id: int) -> None:
    with db_session() as conn:
        cur = conn.execute("DELETE FROM courses WHERE id = ?", (course_id,))
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Course not found")


@app.post("/api/courses/{course_id}/assessments", status_code=status.HTTP_201_CREATED)
def add_assessment(course_id: int, payload: AssessmentCreate) -> dict[str, Any]:
    with db_session() as conn:
        _ensure_course_exists(conn, course_id)
        rec_date = payload.recorded_date or date.today().isoformat()
        conn.execute(
            "INSERT INTO assessments (course_id, title, category, score, max_score, weight, recorded_date) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                course_id,
                payload.title,
                payload.category,
                payload.score,
                payload.max_score,
                payload.weight,
                rec_date,
            ),
        )
        courses = compute_course_metrics(conn)
        return next(c for c in courses if c["id"] == course_id)


@app.delete("/api/assessments/{assessment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_assessment(assessment_id: int) -> None:
    with db_session() as conn:
        cur = conn.execute("DELETE FROM assessments WHERE id = ?", (assessment_id,))
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Assessment not found")


# ---------------------------------------------------------------------------
# Tasks & Assignments
# ---------------------------------------------------------------------------
def _fetch_task_row(conn: sqlite3.Connection, task_id: int) -> dict[str, Any]:
    row = conn.execute(
        "SELECT t.id, t.title, t.course_id, t.task_type, t.priority, t.due_date, "
        "t.estimated_minutes, t.notes, t.completed, t.completed_at, t.created_at, "
        "c.code AS course_code, c.color AS course_color "
        "FROM tasks t LEFT JOIN courses c ON t.course_id = c.id WHERE t.id = ?",
        (task_id,),
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Task not found")
    today_iso = date.today().isoformat()
    return {
        "id": row["id"],
        "title": row["title"],
        "course_id": row["course_id"],
        "course_code": row["course_code"],
        "course_color": row["course_color"] or "#64748b",
        "task_type": row["task_type"],
        "priority": row["priority"],
        "due_date": row["due_date"],
        "estimated_minutes": row["estimated_minutes"],
        "notes": row["notes"],
        "completed": bool(row["completed"]),
        "completed_at": row["completed_at"],
        "created_at": row["created_at"],
        "is_overdue": bool(row["completed"] == 0 and row["due_date"] and row["due_date"] < today_iso),
    }


@app.get("/api/tasks")
def list_tasks(
    status_filter: str = Query(default="all", alias="status"),
    course_id: Optional[int] = Query(default=None),
    priority: Optional[str] = Query(default=None),
    q: Optional[str] = Query(default=None),
) -> list[dict[str, Any]]:
    today_iso = date.today().isoformat()
    conditions: list[str] = []
    params: list[Any] = []

    if status_filter == "active":
        conditions.append("t.completed = 0")
    elif status_filter == "completed":
        conditions.append("t.completed = 1")
    elif status_filter == "overdue":
        conditions.append("t.completed = 0 AND t.due_date IS NOT NULL AND t.due_date < ?")
        params.append(today_iso)

    if course_id is not None:
        conditions.append("t.course_id = ?")
        params.append(course_id)
    if priority:
        conditions.append("t.priority = ?")
        params.append(priority)
    if q and q.strip():
        like = f"%{q.strip()}%"
        conditions.append("(t.title LIKE ? OR t.notes LIKE ?)")
        params.extend([like, like])

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    sql = (
        "SELECT t.id, t.title, t.course_id, t.task_type, t.priority, t.due_date, "
        "t.estimated_minutes, t.notes, t.completed, t.completed_at, t.created_at, "
        "c.code AS course_code, c.color AS course_color "
        f"FROM tasks t LEFT JOIN courses c ON t.course_id = c.id {where_clause} "
        "ORDER BY t.completed ASC, "
        "CASE WHEN t.due_date IS NULL THEN 1 ELSE 0 END ASC, "
        "t.due_date ASC, "
        "CASE t.priority WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END ASC, "
        "t.id DESC"
    )
    with db_session() as conn:
        rows = conn.execute(sql, params).fetchall()
        return [
            {
                "id": r["id"],
                "title": r["title"],
                "course_id": r["course_id"],
                "course_code": r["course_code"],
                "course_color": r["course_color"] or "#64748b",
                "task_type": r["task_type"],
                "priority": r["priority"],
                "due_date": r["due_date"],
                "estimated_minutes": r["estimated_minutes"],
                "notes": r["notes"],
                "completed": bool(r["completed"]),
                "completed_at": r["completed_at"],
                "created_at": r["created_at"],
                "is_overdue": bool(r["completed"] == 0 and r["due_date"] and r["due_date"] < today_iso),
            }
            for r in rows
        ]


@app.post("/api/tasks", status_code=status.HTTP_201_CREATED)
def create_task(payload: TaskCreate) -> dict[str, Any]:
    with db_session() as conn:
        _ensure_course_exists(conn, payload.course_id)
        cur = conn.execute(
            "INSERT INTO tasks (title, course_id, task_type, priority, due_date, "
            "estimated_minutes, notes, completed, completed_at, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, 0, NULL, ?)",
            (
                payload.title,
                payload.course_id,
                payload.task_type,
                payload.priority,
                payload.due_date,
                payload.estimated_minutes,
                payload.notes,
                _utc_now(),
            ),
        )
        return _fetch_task_row(conn, int(cur.lastrowid))


@app.patch("/api/tasks/{task_id}")
def update_task(task_id: int, payload: TaskUpdate) -> dict[str, Any]:
    with db_session() as conn:
        existing = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="Task not found")

        updates: dict[str, Any] = {}
        if payload.title is not None:
            updates["title"] = payload.title.strip()
        if payload.clear_course:
            updates["course_id"] = None
        elif payload.course_id is not None:
            _ensure_course_exists(conn, payload.course_id)
            updates["course_id"] = payload.course_id
        if payload.task_type is not None:
            updates["task_type"] = payload.task_type
        if payload.priority is not None:
            updates["priority"] = payload.priority
        if payload.clear_due_date:
            updates["due_date"] = None
        elif payload.due_date is not None:
            updates["due_date"] = payload.due_date
        if payload.estimated_minutes is not None:
            updates["estimated_minutes"] = payload.estimated_minutes
        if payload.notes is not None:
            updates["notes"] = payload.notes.strip()
        if payload.completed is not None:
            updates["completed"] = 1 if payload.completed else 0
            updates["completed_at"] = _utc_now() if payload.completed else None

        if updates:
            set_clause = ", ".join(f"{col} = ?" for col in updates)
            conn.execute(
                f"UPDATE tasks SET {set_clause} WHERE id = ?",
                (*updates.values(), task_id),
            )
        return _fetch_task_row(conn, task_id)


@app.delete("/api/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(task_id: int) -> None:
    with db_session() as conn:
        cur = conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Task not found")


# ---------------------------------------------------------------------------
# Study Sessions
# ---------------------------------------------------------------------------
@app.get("/api/sessions")
def list_sessions(limit: int = Query(default=30, ge=1, le=200)) -> list[dict[str, Any]]:
    with db_session() as conn:
        rows = conn.execute(
            "SELECT s.id, s.course_id, s.task_id, s.duration_minutes, s.session_date, "
            "s.mode, s.notes, s.created_at, "
            "c.code AS course_code, c.color AS course_color, t.title AS task_title "
            "FROM study_sessions s "
            "LEFT JOIN courses c ON s.course_id = c.id "
            "LEFT JOIN tasks t ON s.task_id = t.id "
            "ORDER BY s.session_date DESC, s.id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [
            {
                "id": r["id"],
                "course_id": r["course_id"],
                "course_code": r["course_code"] or "General",
                "course_color": r["course_color"] or "#64748b",
                "task_id": r["task_id"],
                "task_title": r["task_title"],
                "duration_minutes": r["duration_minutes"],
                "session_date": r["session_date"],
                "mode": r["mode"],
                "notes": r["notes"],
                "created_at": r["created_at"],
            }
            for r in rows
        ]


@app.post("/api/sessions", status_code=status.HTTP_201_CREATED)
def create_session(payload: StudySessionCreate) -> dict[str, Any]:
    with db_session() as conn:
        _ensure_course_exists(conn, payload.course_id)
        _ensure_task_exists(conn, payload.task_id)

        session_date = payload.session_date or date.today().isoformat()
        cur = conn.execute(
            "INSERT INTO study_sessions "
            "(course_id, task_id, duration_minutes, session_date, mode, notes, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                payload.course_id,
                payload.task_id,
                payload.duration_minutes,
                session_date,
                payload.mode,
                payload.notes.strip(),
                _utc_now(),
            ),
        )
        sid = int(cur.lastrowid)

        if payload.complete_task and payload.task_id is not None:
            conn.execute(
                "UPDATE tasks SET completed = 1, completed_at = ? WHERE id = ?",
                (_utc_now(), payload.task_id),
            )

        row = conn.execute(
            "SELECT s.id, s.course_id, s.task_id, s.duration_minutes, s.session_date, "
            "s.mode, s.notes, s.created_at, "
            "c.code AS course_code, c.color AS course_color, t.title AS task_title "
            "FROM study_sessions s "
            "LEFT JOIN courses c ON s.course_id = c.id "
            "LEFT JOIN tasks t ON s.task_id = t.id WHERE s.id = ?",
            (sid,),
        ).fetchone()
        return {
            "id": row["id"],
            "course_id": row["course_id"],
            "course_code": row["course_code"] or "General",
            "course_color": row["course_color"] or "#64748b",
            "task_id": row["task_id"],
            "task_title": row["task_title"],
            "duration_minutes": row["duration_minutes"],
            "session_date": row["session_date"],
            "mode": row["mode"],
            "notes": row["notes"],
            "created_at": row["created_at"],
        }


@app.delete("/api/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_session(session_id: int) -> None:
    with db_session() as conn:
        cur = conn.execute("DELETE FROM study_sessions WHERE id = ?", (session_id,))
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Study session not found")


# ---------------------------------------------------------------------------
# Habits
# ---------------------------------------------------------------------------
@app.get("/api/habits")
def list_habits() -> dict[str, Any]:
    with db_session() as conn:
        return compute_habits_with_grid(conn)


@app.post("/api/habits", status_code=status.HTTP_201_CREATED)
def create_habit(payload: HabitCreate) -> dict[str, Any]:
    with db_session() as conn:
        cur = conn.execute(
            "INSERT INTO habits (title, category, target_days_per_week, created_at) "
            "VALUES (?, ?, ?, ?)",
            (payload.title, payload.category, payload.target_days_per_week, _utc_now()),
        )
        hid = int(cur.lastrowid)
        grid = compute_habits_with_grid(conn)
        return next(h for h in grid["habits"] if h["id"] == hid)


@app.post("/api/habits/{habit_id}/toggle")
def toggle_habit(habit_id: int, payload: HabitToggle) -> dict[str, Any]:
    with db_session() as conn:
        habit = conn.execute("SELECT id FROM habits WHERE id = ?", (habit_id,)).fetchone()
        if not habit:
            raise HTTPException(status_code=404, detail="Habit not found")

        target_date = payload.log_date or date.today().isoformat()
        existing = conn.execute(
            "SELECT id FROM habit_logs WHERE habit_id = ? AND log_date = ?",
            (habit_id, target_date),
        ).fetchone()
        if existing:
            conn.execute("DELETE FROM habit_logs WHERE id = ?", (existing["id"],))
        else:
            conn.execute(
                "INSERT INTO habit_logs (habit_id, log_date) VALUES (?, ?)",
                (habit_id, target_date),
            )
        return compute_habits_with_grid(conn)


@app.delete("/api/habits/{habit_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_habit(habit_id: int) -> None:
    with db_session() as conn:
        cur = conn.execute("DELETE FROM habits WHERE id = ?", (habit_id,))
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Habit not found")


# ---------------------------------------------------------------------------
# Weekly Schedule
# ---------------------------------------------------------------------------
@app.get("/api/schedule")
def list_schedule() -> list[dict[str, Any]]:
    with db_session() as conn:
        rows = conn.execute(
            "SELECT sb.id, sb.title, sb.course_id, sb.day_of_week, sb.start_time, "
            "sb.end_time, sb.block_type, sb.location, "
            "c.code AS course_code, c.color AS course_color "
            "FROM schedule_blocks sb LEFT JOIN courses c ON sb.course_id = c.id "
            "ORDER BY sb.day_of_week ASC, sb.start_time ASC, sb.id ASC"
        ).fetchall()
        return [
            {
                "id": r["id"],
                "title": r["title"],
                "course_id": r["course_id"],
                "course_code": r["course_code"],
                "course_color": r["course_color"] or "#64748b",
                "day_of_week": r["day_of_week"],
                "start_time": r["start_time"],
                "end_time": r["end_time"],
                "block_type": r["block_type"],
                "location": r["location"],
            }
            for r in rows
        ]


@app.post("/api/schedule", status_code=status.HTTP_201_CREATED)
def create_schedule_block(payload: ScheduleBlockCreate) -> dict[str, Any]:
    if payload.end_time <= payload.start_time:
        raise HTTPException(status_code=400, detail="End time must be after start time")
    with db_session() as conn:
        _ensure_course_exists(conn, payload.course_id)
        cur = conn.execute(
            "INSERT INTO schedule_blocks "
            "(title, course_id, day_of_week, start_time, end_time, block_type, location) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                payload.title,
                payload.course_id,
                payload.day_of_week,
                payload.start_time,
                payload.end_time,
                payload.block_type,
                payload.location,
            ),
        )
        bid = int(cur.lastrowid)
        row = conn.execute(
            "SELECT sb.id, sb.title, sb.course_id, sb.day_of_week, sb.start_time, "
            "sb.end_time, sb.block_type, sb.location, "
            "c.code AS course_code, c.color AS course_color "
            "FROM schedule_blocks sb LEFT JOIN courses c ON sb.course_id = c.id "
            "WHERE sb.id = ?",
            (bid,),
        ).fetchone()
        return {
            "id": row["id"],
            "title": row["title"],
            "course_id": row["course_id"],
            "course_code": row["course_code"],
            "course_color": row["course_color"] or "#64748b",
            "day_of_week": row["day_of_week"],
            "start_time": row["start_time"],
            "end_time": row["end_time"],
            "block_type": row["block_type"],
            "location": row["location"],
        }


@app.delete("/api/schedule/{block_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_schedule_block(block_id: int) -> None:
    with db_session() as conn:
        cur = conn.execute("DELETE FROM schedule_blocks WHERE id = ?", (block_id,))
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Schedule block not found")


# ---------------------------------------------------------------------------
# Settings & Data Management
# ---------------------------------------------------------------------------
@app.get("/api/settings")
def get_settings() -> dict[str, Any]:
    with db_session() as conn:
        return _get_settings_dict(conn)


@app.patch("/api/settings")
def update_settings(payload: SettingsUpdate) -> dict[str, Any]:
    with db_session() as conn:
        pairs: dict[str, str] = {}
        if payload.student_name is not None:
            pairs["student_name"] = payload.student_name.strip()
        if payload.semester_label is not None:
            pairs["semester_label"] = payload.semester_label.strip()
        if payload.daily_study_goal_minutes is not None:
            pairs["daily_study_goal_minutes"] = str(payload.daily_study_goal_minutes)
        if payload.default_focus_minutes is not None:
            pairs["default_focus_minutes"] = str(payload.default_focus_minutes)
        if payload.default_break_minutes is not None:
            pairs["default_break_minutes"] = str(payload.default_break_minutes)

        for key, value in pairs.items():
            conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
        return _get_settings_dict(conn)


@app.post("/api/data/seed")
def reset_to_sample_data() -> dict[str, Any]:
    with db_session() as conn:
        seed_sample_data(conn, force=True)
        return {"status": "seeded", "dashboard": build_dashboard_summary(conn)}


@app.post("/api/data/clear")
def clear_workspace_data() -> dict[str, Any]:
    with db_session() as conn:
        clear_all_data(conn)
        return {"status": "cleared", "dashboard": build_dashboard_summary(conn)}


@app.get("/api/data/export")
def export_all_data() -> JSONResponse:
    with db_session() as conn:
        data = {
            "exported_at": _utc_now(),
            "settings": _get_settings_dict(conn),
            "courses": compute_course_metrics(conn),
            "tasks": [dict(r) for r in conn.execute("SELECT * FROM tasks ORDER BY id ASC").fetchall()],
            "study_sessions": [dict(r) for r in conn.execute("SELECT * FROM study_sessions ORDER BY id ASC").fetchall()],
            "habits": [dict(r) for r in conn.execute("SELECT * FROM habits ORDER BY id ASC").fetchall()],
            "habit_logs": [dict(r) for r in conn.execute("SELECT * FROM habit_logs ORDER BY id ASC").fetchall()],
            "schedule_blocks": [dict(r) for r in conn.execute("SELECT * FROM schedule_blocks ORDER BY id ASC").fetchall()],
        }
        return JSONResponse(
            content=data,
            headers={"Content-Disposition": "attachment; filename=scholarflow-backup.json"},
        )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run("app:app", host="127.0.0.1", port=port, reload=False)
