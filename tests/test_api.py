import pytest
from langchain_core.messages import AIMessage, HumanMessage

from student_agent.api import create_app
from student_agent.agent.student_agent import StudentAgent


@pytest.fixture
def client(agent):
    return create_app(agent).test_client()


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200 and r.get_json() == {"status": "ok"}


def test_root_and_docs(client):
    assert client.get("/").status_code == 200
    assert client.get("/").mimetype == "text/html"
    r = client.get("/docs")
    assert r.status_code == 200
    assert r.mimetype == "text/html"
    assert b"SwaggerUIBundle" in r.data


def test_openapi_spec(client):
    r = client.get("/openapi.json")
    assert r.status_code == 200
    spec = r.get_json()
    assert spec["openapi"] == "3.0.3"
    assert "/students/{student_id}/chat" in spec["paths"]


def test_student_data_by_id(client):
    r = client.get("/students/1003")
    assert r.status_code == 200
    body = r.get_json()
    assert body["snapshot"]["profile"]["student_id"] == 1003
    assert body["snapshot"]["profile"]["name"] == "Mona Adel"
    assert body["risk"]["level"] == "high"


def test_different_ids_give_different_students(client):
    a = client.get("/students/1001").get_json()["snapshot"]["profile"]["name"]
    b = client.get("/students/1004").get_json()["snapshot"]["profile"]["name"]
    assert a != b


def test_unknown_student_is_404(client):
    r = client.get("/students/999999")
    assert r.status_code == 404 and "999999" in r.get_json()["error"]


@pytest.mark.parametrize("bad", ["abc", "0", "-5", "1.5"])
def test_bad_student_id_is_400(client, bad):
    assert client.get(f"/students/{bad}").status_code == 400


def test_assessment_without_llm(client):
    r = client.get("/students/1004/assessment?use_llm=false")
    assert r.status_code == 200
    body = r.get_json()
    assert body["risk_level"] == "critical" and body["advice_source"] == "rule_based"


def test_assessment_arabic_flag_and_bad_lang(client):
    assert client.get("/students/1001/assessment?use_llm=false&lang=ar").get_json()["language"] == "ar"
    assert client.get("/students/1001/assessment?lang=fr").status_code == 400
    assert client.get("/students/1001/assessment?use_llm=maybe").status_code == 400


def test_assessment_with_llm_but_no_key_is_503(client):
    r = client.get("/students/1001/assessment")
    assert r.status_code == 503 and "GROQ_API_KEY" in r.get_json()["error"]


def test_unknown_route_and_method(client):
    assert client.get("/nope").status_code == 404
    assert client.post("/students/1001").status_code == 405


class _FakeAgent(StudentAgent):
    def chat(self, student_id, message, history=None):
        self.seen = (student_id, message, history)
        msgs = list(history or []) + [HumanMessage(content=message), AIMessage(content="hi there")]
        return "hi there", msgs


def test_chat_round_trip(service, settings):
    fake = _FakeAgent(service, settings)
    client = create_app(fake).test_client()
    r = client.post("/students/1002/chat", json={"message": "  hello  "})
    assert r.status_code == 200
    body = r.get_json()
    assert body["reply"] == "hi there"
    assert body["history"] == [{"role": "user", "content": "hello"},
                               {"role": "assistant", "content": "hi there"}]
    r2 = client.post("/students/1002/chat", json={"message": "again", "history": body["history"]})
    assert r2.status_code == 200 and len(fake.seen[2]) == 2 and fake.seen[0] == 1002


@pytest.mark.parametrize("payload", [
    None, [], {}, {"message": ""}, {"message": 5},
    {"message": "x", "history": "no"}, {"message": "x", "history": [{"role": "bot", "content": "a"}]},
    {"message": "x", "history": [{"role": "user"}]},
])
def test_chat_validation(client, payload):
    r = client.post("/students/1001/chat", json=payload) if payload is not None \
        else client.post("/students/1001/chat", data="not json", content_type="application/json")
    assert r.status_code == 400


def test_chat_unknown_student_is_404(client):
    # the id is validated before any model is built, so this is 404 even without an API key
    r = client.post("/students/999999/chat", json={"message": "hi"})
    assert r.status_code == 404
