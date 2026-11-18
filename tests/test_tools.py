from student_agent.agent.tools import make_tools


def _tools(service, sid):
    return {t.name: t for t in make_tools(service, sid)}


def test_tools_are_bound_to_one_student(service):
    t = _tools(service, 1003)
    assert t["get_risk_overview"].invoke({})["student"]["name"] == "Mona Adel"
    assert "student_id" not in t["get_risk_overview"].args       # the model cannot choose another student


def test_course_lookup_partial_and_not_found(service):
    t = _tools(service, 1003)
    assert t["get_course_details"].invoke({"course_name": "databases"})["course"] == "Databases"
    err = t["get_course_details"].invoke({"course_name": "Quantum Physics"})
    assert "error" in err and "Databases" in err["available_courses"]


def test_ambiguous_course_asks_for_clarification(service):
    # 'Calculus 1' is finished; 'S' matches several courses
    err = _tools(service, 1003)["get_course_details"].invoke({"course_name": "s"})
    assert "error" in err and len(err["matches"]) > 1


def test_what_score_do_i_need(service):
    out = _tools(service, 1003)["what_score_do_i_need"].invoke({"course_name": "Databases", "target_percent": 50})
    assert out["verdict"] == "possible" and 0 < out["needed_on_remaining_pct"] < 100
    # a perfect total (100%) is out of reach for a student who has already lost many points
    out = _tools(service, 1004)["what_score_do_i_need"].invoke({"course_name": "Databases", "target_percent": 100})
    assert out["verdict"] == "out_of_reach"


def test_tasks_and_resources(service):
    t = _tools(service, 1004)
    assert len(t["get_tasks"].invoke({})["overdue"]) >= 3
    assert t["get_study_resources"].invoke({})["resources"]
