"""The data-access contract. The agent depends on this interface, not on a database.

To connect the real database later, write a class with these three methods
(e.g. ``PostgresRepository``) that runs the SELECTs for the tables listed in
``domain/models.py`` and returns the same models. Nothing else changes.
"""
from __future__ import annotations

from datetime import date
from typing import Protocol, runtime_checkable

from ..domain.models import StudentProfile, StudentRecords


class StudentNotFound(LookupError):
    """Raised when a student id does not exist."""


@runtime_checkable
class StudentRepository(Protocol):
    def as_of(self) -> date | None:
        """The 'today' of the data (fake data is frozen in time); None means use the real date."""

    def list_students(self) -> list[StudentProfile]:
        """All students (used by batch risk scans)."""

    def get_student_records(self, student_id: int) -> StudentRecords:
        """All records of one student. Raises StudentNotFound."""
