"""Temporary repository backed by data/fake_db.json (same table shapes as the real schema)."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from ..domain import models as m
from .repository import StudentNotFound


class JsonRepository:
    def __init__(self, path: str | Path):
        self._path = Path(path)
        with self._path.open(encoding="utf-8") as f:
            self._db = json.load(f)

        self._departments = {d["dept_id"]: d["name"] for d in self._db["departments"]}
        self._names = {a["student_id"]: a["name"] for a in self._db["accounts"]}
        self._students = {s["student_id"]: s for s in self._db["students"]}
        self._courses = {c["course_id"]: m.Course(**c) for c in self._db["courses"]}

    # -- StudentRepository -------------------------------------------------------
    def as_of(self) -> date | None:
        raw = self._db.get("meta", {}).get("as_of")
        return date.fromisoformat(raw) if raw else None

    def list_students(self) -> list[m.StudentProfile]:
        return [self._profile(sid) for sid in sorted(self._students)]

    def get_student_records(self, student_id: int) -> m.StudentRecords:
        if student_id not in self._students:
            raise StudentNotFound(f"No student with id {student_id}")

        enrollments = [
            m.Enrollment(**e) for e in self._db["user_courses"] if e["student_id"] == student_id
        ]
        uc_ids = {e.user_course_id for e in enrollments}
        course_ids = {e.course_id for e in enrollments}

        return m.StudentRecords(
            profile=self._profile(student_id),
            enrollments=enrollments,
            courses={cid: self._courses[cid] for cid in course_ids},
            grades={
                g["user_course_id"]: m.CourseGrade(**g)
                for g in self._db["course_grades"]
                if g["user_course_id"] in uc_ids
            },
            assessments=[
                m.Assessment(**a) for a in self._db["assessments"] if a["user_course_id"] in uc_ids
            ],
            lectures=[m.Lecture(**l) for l in self._db["lectures"] if l["course_id"] in course_ids],
            attendance=[
                m.LectureAttendance(**a)
                for a in self._db["lecture_attendance"]
                if a["user_course_id"] in uc_ids
            ],
            tasks=[m.Task(**t) for t in self._db["tasks"] if t["student_id"] == student_id],
            gpa_entries=[
                m.GpaEntry(**g) for g in self._db["gpa_entries"] if g["student_id"] == student_id
            ],
            materials=[
                m.CourseMaterial(**x) for x in self._db["course_materials"] if x["course_id"] in course_ids
            ],
            links=[m.CourseLink(**x) for x in self._db["course_links"] if x["course_id"] in course_ids],
        )

    # -- helpers -----------------------------------------------------------------
    def _profile(self, student_id: int) -> m.StudentProfile:
        s = self._students[student_id]
        return m.StudentProfile(
            student_id=student_id,
            name=self._names.get(student_id, f"Student {student_id}"),
            department=self._departments.get(s["dept_id"], "Unknown"),
            enrolled_since=s.get("created_at"),
        )
