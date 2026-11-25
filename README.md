# ScholarFlow — Student Performance & Study Tracker

ScholarFlow is a local-first web application built with **FastAPI**, **SQLite**, and a responsive vanilla **HTML/CSS/JS** dashboard designed to help students boost academic performance and manage daily study life in one place.

## Features

- **Performance Index & Overview**: Real-time composite score (0–100) across Focus Rhythm, Task Execution, Habit Consistency, and Academic Standing, paired with actionable coaching tips and a 7-day stacked focus activity chart.
- **Tasks & Deadlines**: Track assignments, exams, projects, and readings with priority levels, due-date countdowns, course tags, search, and status filtering.
- **Courses & Grade Projections**: Calculate credit-weighted GPA, current course averages, and the exact average needed across remaining syllabus weight to hit each course's target grade.
- **Deep Focus Timer & Study Log**: Built-in Pomodoro / custom focus timer linked to specific courses and tasks, automatic session logging, optional task auto-completion, and course time distribution charts.
- **Daily Habits Grid**: Rolling 7-day habit checkoff matrix with per-habit streak tracking.
- **Weekly Schedule**: 7-day (Mon–Sun) class, lab, and study block planner highlighting today's schedule.
- **Dark Mode & JSON Backup**: Toggle light/dark themes, customize study goals, or export your entire database as JSON.

## Running Locally

From `C:\Users\umang\.gemini\antigravity\scratch\scholar-tracker`:

```powershell
python app.py
```

Then open [http://127.0.0.1:8000](http://127.0.0.1:8000) in your browser.

## Running Automated Tests

```powershell
python -m unittest discover -s tests -v
```
