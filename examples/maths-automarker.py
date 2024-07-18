import json
from operator import itemgetter
from typing import TypedDict

import requests
import typer
from sympy import Derivative, Integral, simplify
from sympy.parsing.latex import parse_latex

# PROCESSED HANDWRITING AUTOMARKER
# Award a compound mark to 'processed handwriting' questions.
# The compound mark is calculated according to the option->partial_mark
# mapping defined by the 'processed_handwriting_mark_scheme' variable below.
# Only record a mark for a section if:
#     - no mark exists for it yet AND
#     - an answer has been entered and saved by the candidate
#
# Example 1: Section (i) is awarded full marks for the first task if the candidate enters an expression
# semantically equivalent to (x^3)/3 + c. Full marks are awarded for the second task if the candidate enters
# an expression semantically equivalent to 2x (for example x + x, x * 2 etc. would be valid solutions).
# In this example, we also explicitly assign 0 marks for answers to task 1-3-1-1 consisting of a plain unsolved integral (which would otherwise be
# considered mathematically equivalent to the sample answer). This is by way of showing how to catch nasty corner cases.
#
# ----------------------------------
# ...
# i:
#     maximum mark: 30
#     ...
#       tasks:
#       - instructions: |
#           Enter the integral of $x^2$.
#         type: processed handwriting
#       - instructions: |
#           Enter the derivative of $x^2$.
#         type: processed handwriting
#
# ------------------------------------


class MarkPayload(TypedDict):
    mark: float
    feedback: str


students_url = "/students"
questions_url = "/questions"


def lookup_key(*tokens):
    return "-".join(map(str, tokens))


def build_lookup_table(items):
    keys = lambda i: [k for k in ["question", "part", "section", "task"] if k in i]
    return {lookup_key(*itemgetter(*keys(i))(i)): i for i in items}


def make_request(url, method="get", params=None, data=None):
    res = getattr(requests, method)(url, params=params, data=data)
    if res.status_code == requests.codes.ok:
        return res.json()
    raise Exception(f"Request for '{url}' failed with status code {res.status_code}")


# ^ Helpers ^ ==========================================================================================
# You should not need to modify the above functions.

processed_handwriting_mark_scheme = {
    "1-3-1-1": {
        "answer": "x^3/3 + C",
        "mark": 20,
        "corner_cases": [
            {
                "check": lambda a: a.has(Integral),
                "feedback": "- Solution should not contain unsolved integral",
            }
        ],
    },
    "1-3-1-2": {"answer": "2x", "mark": 10},
}


model_answer = r"\frac{\pi}{2} \tanh \frac{\pi}{2}"


class Automarker:
    def __init__(self, marks: dict[str, dict], answers: dict[str, dict]):
        self.marks = marks
        self.answers = answers

    def run(self, username: str, section_id: str, max_mark: int, tasks: list[dict]):
        if self.marks.get(section_id) is None:
            mark = 0
            has_maths_task, has_answer = False, False
            feedback = ["- Awarded designated marks for answer."]
            for t, task in enumerate(tasks, 1):
                if task["type"] == "PROCESSED_HANDWRITING":
                    matched_corner_case = False
                    has_maths_task = True
                    task_id = lookup_key(section_id, t)
                    answer = self.answers.get(task_id, {}).get("answer")
                    task_mark_scheme = processed_handwriting_mark_scheme.get(task_id)
                    raw_answer = self.answers.get(task_id, {}).get("answer")
                    answer = json.loads(raw_answer).get("latex") if raw_answer else None
                    if task_mark_scheme and answer:
                        has_answer = True
                        given_answer = parse_latex(answer)
                        sample_answer = parse_latex(task_mark_scheme["answer"])
                        for corner_case in task_mark_scheme.get("corner_cases", []):
                            if corner_case["check"](given_answer):
                                matched_corner_case = True
                                feedback.append(corner_case["feedback"])
                        if not matched_corner_case:
                            if simplify(given_answer - sample_answer) == 0:
                                mark += task_mark_scheme["mark"]

            if has_maths_task and has_answer:
                mark = max(0, mark)
                mark = min(max_mark, mark)
                return {
                    "mark": mark,
                    "feedback": "\n".join(feedback),
                }

        return None


def main(
    root_url: str = typer.Argument(
        ...,
        help="Root URL of your answerbook exam e.g. http://answerbook.doc.ic.ac.uk/2023/60005/exam/api",
    ),
):
    questions = make_request(root_url + questions_url)
    students = make_request(root_url + students_url)
    for student in students:
        username = student["username"]
        marks_url = root_url + f"/{username}/marks"

        # Build lookup tables to find if
        # a mark already exists for the given student and a given question-part-section combination;
        # an answer exists for the given student and a given question-part-section-task combination
        mark_lookup = build_lookup_table(make_request(marks_url))
        ans_lookup = build_lookup_table(make_request(root_url + f"/{username}/answers"))
        automarker = Automarker(mark_lookup, ans_lookup)

        for q, question in questions.items():
            for p, parts in question["parts"].items():
                for s, section in parts["sections"].items():
                    section_id = lookup_key(q, p, s)
                    max_mark = section["maximum_mark"]
                    tasks = section["tasks"]
                    ###################################################################
                    # This is where the mark for the task is autogenerated.
                    # The output is a dict shaped as `MarkPayload` (above)
                    # that we then enrich with question, part and section for POSTing.
                    payload = automarker.run(username, section_id, max_mark, tasks)
                    ###################################################################
                    if payload is not None:
                        payload = {
                            **payload,
                            "question": q,
                            "part": p,
                            "section": s,
                        }

                        try:
                            make_request(marks_url, "post", data=json.dumps(payload))
                            print(f"mark saved for {username} on {section_id}")
                        except Exception:
                            print(f"mark not saved for {username} on {section_id}")


if __name__ == "__main__":
    typer.run(main)
