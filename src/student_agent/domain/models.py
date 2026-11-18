"""Row models for the tables the agent needs.

Only the tables and columns listed here are read. The agent never touches
passwords, emails, sessions, notes, the campus map, beacons or analytics tables.
"""
from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field


# ---- tables -------------------------------------------------------------------
class StudentProfile(BaseModel):
    """students + departments.name + accounts.name (joined)."""

    student_id: int
    name: str
    department: str
    enrolled_since: date | None = None


class Course(BaseModel):  # courses
    course_id: int
    dept_id: int | None = None
    name: str
    type: str
    credit_hours: float | None = None


class Enrollment(BaseModel):  # user_courses
    user_course_id: int
    student_id: int
    course_id: int
    enrollment_date: date | None = None
    completed: bool = False
    completion_date: date | None = None


class CourseGrade(BaseModel):  # course_grades (scores are percentages 0-100)
    user_course_id: int
    midterm: float | None = None
    final: float | None = None


class Assessment(BaseModel):  # assessments
    assessment_id: int
    user_course_id: int
    type: str  # quiz / assignment
    name: str
    score: float | None = None
    max_score: float
    weight: float = 1.0
    due_date: date
    submitted_at: datetime | None = None


class Lecture(BaseModel):  # lectures
    lecture_id: int
    course_id: int
    name: str
    lecture_date: date


class LectureAttendance(BaseModel):  # lecture_attendance
    user_course_id: int
    lecture_id: int
    attended: bool


class Task(BaseModel):  # tasks
    task_id: int
    student_id: int
    description: str
    severity: str = "medium"
    deadline: datetime
    completed: bool = False


class GpaEntry(BaseModel):  # gpa_entries
    entry_id: int
    student_id: int
    course_name: str
    credit_hours: float
    grade: str  # letter grade


class CourseMaterial(BaseModel):  # course_materials (title and category only)
    material_id: int
    course_id: int
    category: str
    title: str


class CourseLink(BaseModel):  # course_links
    link_id: int
    course_id: int
    title: str
    url: str


# ---- aggregate returned by the repository ---------------------------------------
class StudentRecords(BaseModel):
    """Everything the agent may read about ONE student, fetched in one call."""

    profile: StudentProfile
    enrollments: list[Enrollment] = Field(default_factory=list)
    courses: dict[int, Course] = Field(default_factory=dict)             # by course_id
    grades: dict[int, CourseGrade] = Field(default_factory=dict)         # by user_course_id
    assessments: list[Assessment] = Field(default_factory=list)
    lectures: list[Lecture] = Field(default_factory=list)                # lectures of enrolled courses
    attendance: list[LectureAttendance] = Field(default_factory=list)
    tasks: list[Task] = Field(default_factory=list)
    gpa_entries: list[GpaEntry] = Field(default_factory=list)
    materials: list[CourseMaterial] = Field(default_factory=list)
    links: list[CourseLink] = Field(default_factory=list)
