import json
from operator import itemgetter
from typing import TypedDict

import requests
import typer

# NO-ANSWER AUTOMARKER
# Award 0 marks to any section iff none of the section's tasks was answered.
# The mark is only recorded for a section if no mark exists for it yet.


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


class Automarker:
    def __init__(self, marks: dict[str, dict], answers: dict[str, dict]):
        self.marks = marks
        self.answers = answers

    def run(self, username: str, section_id: str, max_mark: int, tasks: list[dict]):
        if self.marks.get(section_id) is None:
            if all(
                self.answers.get(lookup_key(section_id, t + 1)) is None
                for t in range(len(tasks))
            ):
                return {"mark": 0, "feedback": "No answer submitted"}
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

        mark_lookup = build_lookup_table(make_request(marks_url))
        ans_lookup = build_lookup_table(make_request(root_url + f"/{username}/answers"))
        automarker = Automarker(mark_lookup, ans_lookup)

        for q, question in questions.items():
            for p, parts in question["parts"].items():
                for s, section in parts["sections"].items():
                    section_id = lookup_key(q, p, s)
                    max_mark = section["maximum_mark"]
                    tasks = section["tasks"]
                    payload = automarker.run(username, section_id, max_mark, tasks)
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
