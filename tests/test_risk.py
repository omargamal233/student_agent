import pytest

from student_agent.analytics.risk import RiskLevel


@pytest.mark.parametrize("student_id, expected", [
    (1001, RiskLevel.LOW),
    (1002, RiskLevel.MODERATE),
    (1003, RiskLevel.HIGH),
    (1004, RiskLevel.CRITICAL),
    (1005, RiskLevel.LOW),
    (1006, RiskLevel.HIGH),      # good grades, but attendance below the minimum in two courses
])
def test_fake_students_land_in_expected_level(service, student_id, expected):
    assert service.analyze(student_id).risk.level == expected


def test_score_is_ordered_by_severity(service):
    scores = {sid: service.analyze(sid).risk.score for sid in (1001, 1002, 1003, 1004)}
    assert scores[1001] < scores[1002] < scores[1003] < scores[1004]


def test_missing_data_lowers_coverage_not_score(service):
    r = service.analyze(1005).risk
    assert r.data_coverage < 1.0
    assert service.analyze(1005).snapshot.data_gaps


def test_hidden_risk_is_flagged(service):
    r = service.analyze(1006).risk
    assert len(r.flags) == 2 and all("Attendance" in f for f in r.flags)


def test_factor_contributions_add_up_to_score(service):
    r = service.analyze(1003).risk
    assert sum(f.contribution for f in r.factors) == pytest.approx(r.score, abs=0.5)
