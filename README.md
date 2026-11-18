# Student Intelligence Agent

Part of the Eng Hub platform. For one student, the agent reads their academic records and:

1. **tells whether there is a risk of dropping out** (level + 0-100 score + the exact reasons), and
2. **gives personal advice** to improve (prioritised actions, a plan for the coming week, study resources),
3. **answers follow-up questions** in chat (Arabic, English or mixed), using tools so every number comes from the data.

Extra ideas added: a *"what score do I need?"* calculator (e.g. the final-exam mark needed to pass or to reach 70%),
study resources picked for the weakest courses, Arabic output, a rule-based fallback when the LLM is down, and a
data-coverage indicator so missing data is shown instead of hidden.

Built with **LangChain** (`create_agent`, tools, structured output) and **Groq** (`openai/gpt-oss-120b`). LangGraph is not
needed.

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
cp .env.example .env                                    # then put your GROQ_API_KEY in it

python -m student_agent                                 # starts the API on http://127.0.0.1:8000
pytest                                                  # all tests, offline
```

Open http://127.0.0.1:8000/docs for interactive Swagger UI, or
http://127.0.0.1:8000/openapi.json for the OpenAPI specification.

On Windows, if `python` is not recognized, use the Python launcher instead (for example, `py -3.14 -m student_agent`).
Change the address with `API_HOST` / `API_PORT` in `.env`. The built-in server is for development; in production run
it with a WSGI server, e.g. `gunicorn "student_agent.api:create_app()"`.

## API

The caller sends the **student id** and gets that student's data. Errors are JSON: `{"error": "..."}`.

| Method and path | What it returns | Needs LLM key |
| --- | --- | --- |
| `GET /health` | `{"status": "ok"}` | no |
| `GET /students/{id}` | profile, numbers per course, risk score/level/factors, study resources | no |
| `GET /students/{id}/assessment?lang=en\|ar&use_llm=true\|false` | full report with advice (`use_llm=false` gives rule-based advice) | only if `use_llm=true` |
| `POST /students/{id}/chat` | `{"message": "...", "history": [...]}` -> `{"reply": "...", "history": [...]}` | yes |

```bash
curl http://127.0.0.1:8000/students/1003
curl "http://127.0.0.1:8000/students/1003/assessment?lang=ar"
curl -X POST http://127.0.0.1:8000/students/1003/chat \
     -H "Content-Type: application/json" -d '{"message": "What score do I need in Databases?"}'
```

For chat, the server keeps no conversation: send back the `history` you received to continue the conversation.

| Status | When |
| --- | --- |
| 400 | id is not a positive integer, bad `lang` / `use_llm`, bad chat body |
| 404 | no student with that id |
| 503 | the LLM is needed but `GROQ_API_KEY` is not set |

## How it works

```
 repository (fake JSON now, real DB later)
        |  StudentRecords (only the tables the agent needs)
        v
 analytics.features   -> StudentSnapshot   standing, attendance, missed work, trend, needed score, GPA, tasks
        v
 analytics.risk       -> RiskAssessment    score 0-100, level, factors with evidence, hard flags
        v
 services.assessment  -> StudentAnalysis   + study resources
        v
 agent                -> LLM writes advice from the verified facts only (structured output)  -> DropoutReport
                      -> or chat agent with 5 tools bound to ONE student
```

**The LLM never calculates risk.** Numbers and the risk level are computed in plain code (testable, explainable); the LLM
only explains them and writes the advice. If the LLM fails, a rule-based report is returned instead.

## Project structure

```
student-agent/
├── pyproject.toml, requirements.txt, .env.example
├── data/fake_db.json                  TEMPORARY fake data (same table shapes as the real schema)
├── scripts/generate_fake_data.py      regenerates the fake data (6 test students)
├── src/student_agent/
│   ├── config.py                      settings, grading policy, risk weights, level thresholds
│   ├── app.py                         wiring: which repository / risk model / agent to use
│   ├── api.py, __main__.py            HTTP API (Flask) and its entry point
│   ├── domain/models.py               row models of the tables the agent reads
│   ├── data/
│   │   ├── repository.py              the contract (3 methods): swap the data source here
│   │   └── json_repository.py         fake-data implementation
│   ├── analytics/
│   │   ├── features.py                records -> snapshot (pure functions)
│   │   └── risk.py                    HeuristicRiskModel (+ RiskModel protocol for an ML model later)
│   ├── services/assessment.py         records -> analysis (no LLM)
│   └── agent/
│       ├── llm.py                     ChatGroq + structured-output chain
│       ├── prompts.py                 all prompts
│       ├── schemas.py                 AdviceBundle (LLM output) and DropoutReport (final result)
│       ├── facts.py                   what the LLM is allowed to see
│       ├── tools.py                   chat tools, bound to one student
│       ├── fallback.py                rule-based advice
│       └── student_agent.py           StudentAgent: assess() and chat()
└── tests/                             31 offline tests
```

## Tables the agent uses (and nothing else)

`students`, `departments` (name), `accounts` (name only), `courses`, `user_courses`, `course_grades`, `assessments`,
`lectures`, `lecture_attendance`, `tasks`, `gpa_entries`, `course_materials` (title/category), `course_links`.

Not read: passwords, emails, sessions, notes, schedule, the campus map, beacons, live data and analytics tables.

## Risk score

Seven weighted factors; a factor with no data is left out and the others are re-weighted (`data_coverage` shows how much
was available).

| Factor | Weight | Based on |
| --- | --- | --- |
| Academic standing | 0.30 | credit-weighted average and weakest course |
| Lecture attendance | 0.20 | average and lowest course |
| Missed and late work | 0.15 | missed items count as zero, late items count half |
| Recent score trend | 0.10 | later scores vs earlier scores |
| GPA | 0.10 | `gpa_entries` |
| Previous failures | 0.10 | completed courses below the pass mark |
| Overdue tasks | 0.05 | `tasks` |

Levels: **low** < 20, **moderate** < 40, **high** < 60, **critical** >= 60. Hard flags can raise the level:
attendance below the minimum in 1 course -> at least moderate, in 2+ courses -> at least high; a course that cannot reach
the pass mark even with a perfect result on the remaining work -> at least high (2+ courses -> critical).

This is a transparent heuristic, not a trained model. When real historical data exists, train a model and implement the
`RiskModel` protocol (`assess(snapshot) -> RiskAssessment`), then change one line in `app.py`.

## Assumptions to confirm with the faculty (all in `config.py`)

| Assumption | Default |
| --- | --- |
| Pass mark | 50% |
| Course mark = coursework / midterm / final | 40% / 20% / 40% |
| Minimum attendance | 75% |
| `course_grades.midterm` and `final` are percentages (0-100) | yes |
| `assessments.weight` is only a *relative* weight inside coursework | yes |
| `gpa_entries.grade` is a letter grade on a 4.0 scale | yes |
| Coursework graded so far is treated as the full coursework component | yes |

## Fake test data

| ID | Student | Situation | Expected level |
| --- | --- | --- | --- |
| 1001 | Sara Hassan | strong in everything | low |
| 1002 | Omar Khaled | attendance and scores slipping in Databases | moderate |
| 1003 | Mona Adel | weak scores, missed work, one past failure | high |
| 1004 | Youssef Tarek | low attendance everywhere, failing, overdue tasks | critical |
| 1005 | Nour Samir | new student, little data | low (coverage 65%) |
| 1006 | Karim Mahmoud | good grades but attendance below minimum in 2 courses | high |

The data is frozen at 2026-11-18 (`meta.as_of`), so results are reproducible. Links in it are fake (`example.com`).

## Connecting the real database

1. Write `PostgresRepository` (or similar) with the three methods of `data/repository.py`; `get_student_records` runs the
   SELECTs for the tables above and returns the models in `domain/models.py`.
2. In `app.py`, replace `JsonRepository(...)` with it. Nothing else changes.
3. Make sure `course_grades` and `assessments` follow the assumptions above, or adjust `config.py`.

## Status

Tested offline (tests): data layer, calculations, risk levels, tools, report building, fallback, chat loop with a fake
model, and that the Groq client builds with the right model name. **Not tested against the live Groq API** (no network or
key where this was built): call `/assessment` and `/chat` once with your key. If `json_schema` structured output is rejected for
the model, the chain automatically retries with tool-calling (`agent/llm.py`).
