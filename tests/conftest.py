import pytest

from student_agent.agent.schemas import AdviceBundle, AdviceItem, PlanStep
from student_agent.agent.student_agent import StudentAgent
from student_agent.app import build_service
from student_agent.config import Settings


@pytest.fixture(scope="session")
def settings():
    return Settings(_env_file=None, groq_api_key=None)


@pytest.fixture(scope="session")
def service(settings):
    return build_service(settings)


@pytest.fixture
def stub_bundle():
    return AdviceBundle(
        summary="stub summary",
        advice=[AdviceItem(priority=2, title="second", action="a2", why="w2"),
                AdviceItem(priority=1, title="first", action="a1", why="w1", course="Databases")],
        weekly_plan=[PlanStep(when="Thu", step="do it")],
        encouragement="keep going",
    )


@pytest.fixture
def agent(service, settings):
    return StudentAgent(service, settings)
