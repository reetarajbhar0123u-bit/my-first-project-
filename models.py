"""Pydantic request schemas and validation helpers for ScholarFlow."""

from __future__ import annotations

import re
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

HEX_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
TIME_RE = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class CourseCreate(BaseModel):
    code: str = Field(..., min_length=1, max_length=24)
    name: str = Field(..., min_length=1, max_length=120)
    color: str = Field(default="#4f46e5")
    credits: float = Field(default=3.0, ge=0.5, le=12.0)
    target_grade: float = Field(default=90.0, ge=1.0, le=100.0)
    instructor: str = Field(default="", max_length=100)

    @field_validator("code", "name", "instructor")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("color")
    @classmethod
    def validate_color(cls, value: str) -> str:
        val = value.strip()
        if not HEX_COLOR_RE.match(val):
            raise ValueError("Color must be a 6-digit hex code like #4f46e5")
        return val


class CourseUpdate(BaseModel):
    code: Optional[str] = Field(default=None, min_length=1, max_length=24)
    name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    color: Optional[str] = None
    credits: Optional[float] = Field(default=None, ge=0.5, le=12.0)
    target_grade: Optional[float] = Field(default=None, ge=1.0, le=100.0)
    instructor: Optional[str] = Field(default=None, max_length=100)

    @field_validator("color")
    @classmethod
    def validate_color(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        val = value.strip()
        if not HEX_COLOR_RE.match(val):
            raise ValueError("Color must be a 6-digit hex code like #4f46e5")
        return val


class AssessmentCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=120)
    category: Literal["Exam", "Quiz", "Assignment", "Lab", "Project"] = "Assignment"
    score: float = Field(..., ge=0.0, le=10000.0)
    max_score: float = Field(..., gt=0.0, le=10000.0)
    weight: float = Field(..., gt=0.0, le=100.0)
    recorded_date: Optional[str] = None

    @field_validator("title")
    @classmethod
    def strip_title(cls, value: str) -> str:
        return value.strip()

    @field_validator("recorded_date")
    @classmethod
    def validate_date(cls, value: Optional[str]) -> Optional[str]:
        if value is None or value == "":
            return None
        if not DATE_RE.match(value):
            raise ValueError("recorded_date must be YYYY-MM-DD")
        return value


class TaskCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=160)
    course_id: Optional[int] = None
    task_type: Literal["Assignment", "Exam", "Project", "Reading", "Personal"] = "Assignment"
    priority: Literal["high", "medium", "low"] = "medium"
    due_date: Optional[str] = None
    estimated_minutes: int = Field(default=45, ge=5, le=600)
    notes: str = Field(default="", max_length=1000)

    @field_validator("title", "notes")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("due_date")
    @classmethod
    def validate_due_date(cls, value: Optional[str]) -> Optional[str]:
        if value is None or value.strip() == "":
            return None
        val = value.strip()
        if not DATE_RE.match(val):
            raise ValueError("due_date must be YYYY-MM-DD")
        return val


class TaskUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=160)
    course_id: Optional[int] = None
    clear_course: bool = False
    task_type: Optional[Literal["Assignment", "Exam", "Project", "Reading", "Personal"]] = None
    priority: Optional[Literal["high", "medium", "low"]] = None
    due_date: Optional[str] = None
    clear_due_date: bool = False
    estimated_minutes: Optional[int] = Field(default=None, ge=5, le=600)
    notes: Optional[str] = Field(default=None, max_length=1000)
    completed: Optional[bool] = None

    @field_validator("due_date")
    @classmethod
    def validate_due_date(cls, value: Optional[str]) -> Optional[str]:
        if value is None or value.strip() == "":
            return None
        val = value.strip()
        if not DATE_RE.match(val):
            raise ValueError("due_date must be YYYY-MM-DD")
        return val


class StudySessionCreate(BaseModel):
    course_id: Optional[int] = None
    task_id: Optional[int] = None
    duration_minutes: int = Field(..., ge=1, le=600)
    session_date: Optional[str] = None
    mode: Literal["focus", "manual", "review"] = "focus"
    notes: str = Field(default="", max_length=500)
    complete_task: bool = False

    @field_validator("session_date")
    @classmethod
    def validate_session_date(cls, value: Optional[str]) -> Optional[str]:
        if value is None or value.strip() == "":
            return None
        val = value.strip()
        if not DATE_RE.match(val):
            raise ValueError("session_date must be YYYY-MM-DD")
        return val


class HabitCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=120)
    category: Literal["Study", "Wellness", "Organization"] = "Study"
    target_days_per_week: int = Field(default=5, ge=1, le=7)

    @field_validator("title")
    @classmethod
    def strip_title(cls, value: str) -> str:
        return value.strip()


class HabitToggle(BaseModel):
    log_date: Optional[str] = None

    @field_validator("log_date")
    @classmethod
    def validate_date(cls, value: Optional[str]) -> Optional[str]:
        if value is None or value.strip() == "":
            return None
        val = value.strip()
        if not DATE_RE.match(val):
            raise ValueError("log_date must be YYYY-MM-DD")
        return val


class ScheduleBlockCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=120)
    course_id: Optional[int] = None
    day_of_week: int = Field(..., ge=0, le=6)
    start_time: str
    end_time: str
    block_type: Literal["Class", "Study", "Lab", "Activity"] = "Class"
    location: str = Field(default="", max_length=100)

    @field_validator("title", "location")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("start_time", "end_time")
    @classmethod
    def validate_time(cls, value: str) -> str:
        val = value.strip()
        if not TIME_RE.match(val):
            raise ValueError("Time must be HH:MM in 24-hour format")
        return val


class SettingsUpdate(BaseModel):
    student_name: Optional[str] = Field(default=None, min_length=1, max_length=60)
    semester_label: Optional[str] = Field(default=None, min_length=1, max_length=60)
    daily_study_goal_minutes: Optional[int] = Field(default=None, ge=15, le=720)
    default_focus_minutes: Optional[int] = Field(default=None, ge=5, le=120)
    default_break_minutes: Optional[int] = Field(default=None, ge=1, le=60)
