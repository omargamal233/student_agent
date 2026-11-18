import pytest

from student_agent.data.json_repository import JsonRepository
from student_agent.data.repository import StudentNotFound, StudentRepository


def test_json_repository_satisfies_contract(settings):
    repo = JsonRepository(settings.fake_db_path)
    assert isinstance(repo, StudentRepository)
    assert repo.as_of() is not None


def test_records_are_scoped_to_one_student(settings):
    repo = JsonRepository(settings.fake_db_path)
    rec = repo.get_student_records(1001)
    assert rec.profile.name == "Sara Hassan"
    assert {e.student_id for e in rec.enrollments} == {1001}
    assert {t.student_id for t in rec.tasks} <= {1001}
    uc_ids = {e.user_course_id for e in rec.enrollments}
    assert {a.user_course_id for a in rec.assessments} <= uc_ids


def test_unknown_student(settings):
    with pytest.raises(StudentNotFound):
        JsonRepository(settings.fake_db_path).get_student_records(999999)
