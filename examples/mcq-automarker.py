import json
import os
from collections import defaultdict
from operator import itemgetter
from typing import TypedDict

import requests
import typer
from dotenv import load_dotenv

# MULTIPLE CHOICE QUESTIONS AUTOMARKER
# Award a compound mark to multichoice questions.
# The compound mark is calculated according to the option->partial_mark
# mapping defined by the 'mcq_mark_scheme' variable.
# A negative total is rounded up to 0, and a total higher than the section's maximum mark gets capped at that.
# Only record a mark for a section if:
#     - no mark exists for it yet AND
#     - at least one choice indicated by the candidate
#
# Example 1: Section (i) is awarded 6 marks if the candidate chose 'Option 2' as their answer, 0 otherwise.
# ----------------------------------
# ...
# i:
#     maximum mark: 6
#     ...
#     - task: |
#         What's the answer to the Ultimate Question of Life, the Universe, and Everything?
#         type: 'multiple choice select one'
#         choices:
#             - a: 12
#             - b: 42
#             - c: 32
#             - d: 2
# ------------------------------------
#
#
# Example 2: Marks for section (i) are calculated as the sum of the marks corresponding to the candidate's choices.
# Option (a) carries -1, (b) 2, (c) 1, (d) -2, (e) 3.
# ----------------------------------
# ...
# i:
#     maximum mark: 6
#     ...
#     - task: |
#         Indicate, among the following books, the ones written by Isaac Asimov.
#         type: 'multiple choice select several'
#         choices:
#             - a: "Rendezvous with Rama"
#             - b: "The Gods Themselves"
#             - c: "I, Robot"
#             - d: "IT"
#             - e: "Of Matters Great and Small"
# ------------------------------------


class MarkPayload(TypedDict):
    mark: float
    feedback: str


token_url = "/auth/login"
students_url = "/students"
questions_url = "/questions"
answers_url = "/answers"
marks_url = "/marks"


def lookup_key(*tokens):
    return "-".join(map(str, tokens))


def build_outer_lookup_table(items):
    table = defaultdict(list)
    for item in items:
        table[item["username"]].append(item)
    return table


def build_inner_lookup_table(items):
    keys = lambda i: [k for k in ["question", "part", "section", "task"] if k in i]
    return {lookup_key(*itemgetter(*keys(i))(i)): i for i in items}


def get_token(url) -> str:
    creds = {"username": os.getenv("API_USER"), "password": os.getenv("API_PASSWORD")}
    return make_request(url + token_url, method="post", data=creds)["access_token"]


def make_request(url, method="get", params=None, data=None, access_token=None):
    headers = {"Authorization": f"Bearer {access_token}"} if access_token else None
    res = getattr(requests, method)(url, params=params, data=data, headers=headers)
    if res.status_code == requests.codes.ok:
        return res.json()
    raise Exception(
        f"Request for '{url}' failed with status code {res.status_code}: {res.json()['detail']}"
    )


# ^ Helpers ^ ==========================================================================================
# You should not need to modify the above functions.

mcq_mark_scheme = {
    "1-1-1-1": {"a": 2, "d": 2},
    "1-1-1-2": {"a": 4},
}


class Automarker:
    def __init__(self, marks: dict[str, dict], answers: dict[str, dict]):
        self.marks = marks
        self.answers = answers

    def run(self, username: str, section_id: str, max_mark: int, tasks: list[dict]):
        if self.marks.get(section_id) is None:
            total_section_mark = 0
            section_has_mcq, has_answer = False, False
            for t, task in enumerate(tasks, 1):
                if task["type"].startswith("MULTIPLE_CHOICE"):
                    section_has_mcq = True
                    task_id = lookup_key(section_id, t)
                    answer = self.answers.get(task_id, {}).get("answer")
                    option_mark_table = mcq_mark_scheme[task_id]
                    if option_mark_table and answer:
                        has_answer = True
                        choices = set(answer.split(","))
                        mark_for_task = sum(
                            option_mark_table.get(choice, 0) for choice in choices
                        )
                        total_section_mark += mark_for_task
            if section_has_mcq and has_answer:
                mark = max(0, total_section_mark)
                mark = min(max_mark, mark)
                return {
                    "mark": mark,
                    "feedback": "Awarded designated marks for chosen option(s).",
                }
        return None


def main(
    root_url: str = typer.Argument(
        ...,
        help="Root API URL of your answerbook exam e.g. http://answerbook-api.doc.ic.ac.uk/y2023_12345_exam",
    ),
):
    load_dotenv()

    token = get_token(root_url)
    questions = make_request(root_url + questions_url, access_token=token)
    students = make_request(root_url + students_url, access_token=token)

    # Build lookup tables to find if
    # a mark already exists for the given student and a given question-part-section combination;
    # an answer exists for the given student and a given question-part-section-task combination
    answers = make_request(root_url + answers_url, access_token=token)
    answers_lookup = build_outer_lookup_table(answers)
    answers_lookup = {
        k: build_inner_lookup_table(vs) for k, vs in answers_lookup.items()
    }

    marks = make_request(root_url + answers_url, access_token=token)
    marks_lookup = build_outer_lookup_table(marks)
    marks_lookup = {k: build_inner_lookup_table(vs) for k, vs in marks_lookup.items()}

    for student in students:
        username = student["username"]
        automarker = Automarker(marks_lookup[username], answers_lookup[username])
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
                            "username": username,
                        }

                        try:
                            make_request(
                                root_url + marks_url,
                                "post",
                                data=json.dumps(payload),
                                access_token=token,
                            )
                            print(f"mark saved for {username} on {section_id}")
                        except Exception:
                            print(f"mark not saved for {username} on {section_id}")


if __name__ == "__main__":
    typer.run(main)
