import json
from operator import itemgetter
from typing import TypedDict

import requests
import typer

# MULTIPLE CHOICE QUESTIONS AUTOMARKER
# Award a compound mark to multichoice questions.
# The compound mark is calculated according to the option->partial_mark
# mapping indicated under the 'answer' field of each task. If such a mapping
# is not specified for an option, that option is associated by default to 0.
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
    raise Exception(
        f"Request for '{url}' failed with status code {res.status_code}: {res.json()['detail']}"
    )


# ^ Helpers ^ ==========================================================================================
# You should not need to modify the above functions.

marks_to_mcq_options = {
    "1-1-1-1": {"c": 20, "d": 5},
    "1-2-1-1": {"a": 50},
}


class Automarker:
    def __init__(self, marks: dict[str, dict], answers: dict[str, dict]):
        self.marks = marks
        self.answers = answers

    def run(self, username: str, section_id: str, max_mark: int, tasks: list[dict]):
        if self.marks.get(section_id) is None:
            total_section_mark = 0
            section_has_mcq = False
            for t, task in enumerate(tasks, 1):
                if task["type"].startswith("MULTIPLE_CHOICE"):
                    section_has_mcq = True
                    task_id = lookup_key(section_id, t)
                    answer = self.answers.get(task_id, {}).get("answer")
                    option_mark_table = marks_to_mcq_options[task_id]
                    if option_mark_table and answer:
                        choices = set(answer.split(","))
                        mark_for_task = sum(
                            option_mark_table.get(choice, 0) for choice in choices
                        )
                        total_section_mark += mark_for_task
            if section_has_mcq:
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
