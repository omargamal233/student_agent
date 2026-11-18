"""Generate data/fake_db.json: temporary test data shaped like the real schema.

Only the tables/columns the Student agent reads are generated. Re-run any time:

    python scripts/generate_fake_data.py

The data is frozen at AS_OF so results are reproducible (the JSON stores it in meta.as_of).
"""
from __future__ import annotations

import json
import random
from datetime import date, datetime, timedelta
from pathlib import Path

AS_OF = date(2026, 11, 18)
SEMESTER_START = date(2026, 9, 26)
OUT = Path(__file__).resolve().parents[1] / "data" / "fake_db.json"
rng = random.Random(42)

DEPARTMENTS = [
    "Computer Engineering and Automatic Control", "Electrical Power", "Electronics and Communications",
    "Mechanical Power", "Production", "Architectural", "Civil", "Physics and Mathematics",
]

# course_id: (name, type, credit_hours)
COURSES = {
    1: ("Scientific Thinking", "general", 2),
    2: ("Technical Report Writing", "general", 2),
    3: ("Data Structures", "specialized", 3),
    4: ("Databases", "specialized", 3),
    5: ("Digital Logic Design", "specialized", 3),
    6: ("Signals and Systems", "specialized", 3),
    7: ("Programming Fundamentals", "specialized", 3),   # finished in a past term
    8: ("Calculus 1", "specialized", 3),                 # finished in a past term
}
CURRENT = [1, 2, 3, 4, 5, 6]

# Each persona is a test case for a different situation.
PERSONAS = [
    dict(id=1001, name="Sara Hassan", note="Thriving student",
         att=0.95, mean=86, sd=5, trend=1.0, mid=82, miss=0.0, late=0.05,
         tasks=[("Submit Data Structures assignment 3", "medium", 5, False),
                ("Prepare Databases quiz", "low", 9, False)],
         gpa=[("Programming Fundamentals", 3, "A"), ("Calculus 1", 3, "A-")],
         past=[(7, 88, 90, 86), (8, 82, 85, 84)]),
    dict(id=1002, name="Omar Khaled", note="Slipping: attendance and scores falling in Databases",
         att=0.90, att_over={4: 0.62}, mean=72, sd=6, trend=-2.0, mid=66, miss=0.05, late=0.20,
         mid_over={4: 50},
         tasks=[("Databases assignment 3", "high", 7, False), ("Lab report draft", "medium", -2, False)],
         gpa=[("Programming Fundamentals", 3, "B-"), ("Calculus 1", 3, "C+")],
         past=[(7, 62, 66, 68), (8, 58, 60, 63)]),
    dict(id=1003, name="Mona Adel", note="Struggling: missed work, weak midterms, one past failure",
         att=0.80, mean=56, sd=8, trend=-1.0, mid=50, miss=0.12, late=0.25,
         mid_over={3: 42, 4: 45},
         tasks=[("Data Structures assignment 3", "high", 4, False), ("Databases project proposal", "high", -5, False),
                ("Signals problem sheet", "medium", -3, False)],
         gpa=[("Programming Fundamentals", 3, "C"), ("Calculus 1", 3, "F")],
         past=[(7, 55, 58, 60), (8, 30, 35, 40)]),
    dict(id=1004, name="Youssef Tarek", note="Critical: low attendance everywhere, failing, overdue tasks",
         att=0.45, mean=28, sd=10, trend=-1.0, mid=22, miss=0.55, late=0.30,
         tasks=[("Data Structures assignment 3", "high", 3, False), ("Databases project proposal", "high", -9, False),
                ("Digital Logic lab report", "high", -6, False), ("Signals problem sheet", "medium", -4, False),
                ("Report outline", "medium", -2, False)],
         gpa=[("Programming Fundamentals", 3, "D"), ("Calculus 1", 3, "F")],
         past=[(7, 30, 38, 35), (8, 25, 30, 28)]),
    dict(id=1005, name="Nour Samir", note="New student: very little data",
         courses=[1, 3, 4, 5], att=0.96, no_att={5}, mean=72, sd=5, trend=0, mid=None, miss=0.0, late=0.0,
         few_assessments=2,
         tasks=[], gpa=[], past=[]),
    dict(id=1006, name="Karim Mahmoud", note="Hidden risk: good grades, poor attendance, overdue tasks",
         att=0.85, att_over={3: 0.55, 5: 0.58}, mean=80, sd=5, trend=0.5, mid=78, miss=0.0, late=0.10,
         tasks=[("Data Structures assignment 3", "medium", 6, False), ("Lab report", "medium", -3, False),
                ("Signals problem sheet", "medium", -4, False), ("Databases quiz prep", "low", -1, False)],
         gpa=[("Programming Fundamentals", 3, "B+"), ("Calculus 1", 3, "B")],
         past=[(7, 76, 78, 80), (8, 72, 75, 74)]),
]


def clamp(x, lo=0.0, hi=100.0):
    return max(lo, min(hi, x))


def build() -> dict:
    db: dict = {
        "meta": {"as_of": AS_OF.isoformat(),
                 "note": "FAKE test data shaped like the Eng Hub schema (only the tables the Student agent reads)."},
        "departments": [{"dept_id": i + 1, "name": n} for i, n in enumerate(DEPARTMENTS)],
        "students": [], "accounts": [],
        "courses": [{"course_id": cid, "dept_id": None if t == "general" else 1, "name": n, "type": t,
                     "credit_hours": cr} for cid, (n, t, cr) in COURSES.items()],
        "user_courses": [], "course_grades": [], "assessments": [], "lectures": [],
        "lecture_attendance": [], "tasks": [], "gpa_entries": [],
        "course_materials": [], "course_links": [],
    }

    # lectures: two per week per current course, 16 planned (the last ones are still in the future)
    lecture_id = 1
    lectures_by_course: dict[int, list[dict]] = {}
    for cid in CURRENT:
        lectures_by_course[cid] = []
        for i in range(16):
            d = SEMESTER_START + timedelta(days=7 * (i // 2) + (0 if i % 2 == 0 else 3) + cid % 3)
            row = {"lecture_id": lecture_id, "course_id": cid, "name": f"{COURSES[cid][0]} - Lecture {i + 1}",
                   "lecture_date": d.isoformat()}
            db["lectures"].append(row)
            lectures_by_course[cid].append(row)
            lecture_id += 1

    # study resources (fake links)
    mat_id = link_id = 1
    for cid in CURRENT:
        name = COURSES[cid][0]
        slug = name.lower().replace(" ", "-")
        for cat, title in [("lecture", f"{name} - lecture slides"), ("sheet", f"{name} - problem sheets"),
                           ("exam", f"{name} - previous exams")]:
            db["course_materials"].append({"material_id": mat_id, "course_id": cid, "category": cat, "title": title})
            mat_id += 1
        for title in [f"{name} - video playlist", f"{name} - practice exercises"]:
            db["course_links"].append({"link_id": link_id, "course_id": cid, "title": title,
                                       "url": f"https://example.com/{slug}/{link_id}"})
            link_id += 1

    uc_id = assess_id = task_id = gpa_id = 1
    for p in PERSONAS:
        db["students"].append({"student_id": p["id"], "dept_id": 1, "created_at": "2025-09-20"})
        db["accounts"].append({"account_id": p["id"], "student_id": p["id"], "name": p["name"]})

        # ---- past (finished) courses ----
        for cid, mid, fin, cw in p["past"]:
            db["user_courses"].append({"user_course_id": uc_id, "student_id": p["id"], "course_id": cid,
                                       "enrollment_date": "2025-09-20", "completed": True,
                                       "completion_date": "2026-06-30"})
            db["course_grades"].append({"user_course_id": uc_id, "midterm": mid, "final": fin})
            for k, (kind, mx, w) in enumerate([("quiz", 10, 5), ("assignment", 20, 10), ("quiz", 10, 5)]):
                db["assessments"].append({
                    "assessment_id": assess_id, "user_course_id": uc_id, "type": kind,
                    "name": f"{kind.title()} {k + 1}", "score": round(clamp(cw + rng.gauss(0, 4)) * mx / 100, 1),
                    "max_score": mx, "weight": w, "due_date": (date(2026, 3, 1) + timedelta(days=14 * k)).isoformat(),
                    "submitted_at": datetime.combine(date(2026, 3, 1) + timedelta(days=14 * k),
                                                     datetime.min.time()).replace(hour=10).isoformat()})
                assess_id += 1
            uc_id += 1

        # ---- current courses ----
        for cid in p.get("courses", CURRENT):
            db["user_courses"].append({"user_course_id": uc_id, "student_id": p["id"], "course_id": cid,
                                       "enrollment_date": "2026-09-20", "completed": False,
                                       "completion_date": None})
            mid = p.get("mid_over", {}).get(cid, p["mid"])
            db["course_grades"].append({"user_course_id": uc_id, "midterm": mid, "final": None})

            plan = [("quiz", "Quiz 1", 10, 5, date(2026, 10, 10)), ("assignment", "Assignment 1", 20, 10, date(2026, 10, 17)),
                    ("quiz", "Quiz 2", 10, 5, date(2026, 10, 31)), ("assignment", "Assignment 2", 20, 10, date(2026, 11, 7)),
                    ("quiz", "Quiz 3", 10, 5, date(2026, 11, 14)), ("assignment", "Assignment 3", 20, 10, date(2026, 11, 28))]
            if p.get("few_assessments"):
                plan = plan[: p["few_assessments"]]
            for i, (kind, nm, mx, w, due) in enumerate(plan):
                score, submitted = None, None
                if due <= AS_OF:
                    if rng.random() < p["miss"]:
                        pass                                    # never handed in
                    else:
                        pct = clamp(p["mean"] + p["trend"] * (i - 2) + rng.gauss(0, p["sd"]))
                        score = round(pct * mx / 100, 1)
                        late = rng.random() < p["late"]
                        sub = datetime.combine(due, datetime.min.time()).replace(hour=20)
                        submitted = (sub + timedelta(days=rng.randint(1, 3)) if late else sub - timedelta(hours=rng.randint(2, 40))).isoformat()
                db["assessments"].append({"assessment_id": assess_id, "user_course_id": uc_id, "type": kind,
                                          "name": nm, "score": score, "max_score": mx, "weight": w,
                                          "due_date": due.isoformat(), "submitted_at": submitted})
                assess_id += 1

            if cid not in p.get("no_att", set()):
                prob = p.get("att_over", {}).get(cid, p["att"])
                for lec in lectures_by_course.get(cid, []):
                    if date.fromisoformat(lec["lecture_date"]) <= AS_OF:
                        db["lecture_attendance"].append({"user_course_id": uc_id, "lecture_id": lec["lecture_id"],
                                                         "attended": rng.random() < prob})
            uc_id += 1

        # ---- tasks and GPA entries ----
        for desc, sev, days, done in p["tasks"]:
            dl = datetime.combine(AS_OF + timedelta(days=days), datetime.min.time()).replace(hour=23, minute=59)
            db["tasks"].append({"task_id": task_id, "student_id": p["id"], "description": desc, "severity": sev,
                                "deadline": dl.isoformat(), "completed": done})
            task_id += 1
        for cname, cr, grade in p["gpa"]:
            db["gpa_entries"].append({"entry_id": gpa_id, "student_id": p["id"], "course_name": cname,
                                      "credit_hours": cr, "grade": grade})
            gpa_id += 1
    return db


if __name__ == "__main__":
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(build(), indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {OUT}")
