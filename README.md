# What's this repository about

This repository contains a template and useful examples for creating custom automarkers for your Answerbook exams,
leveraging the Answerbook API. Each script in the `examples` folder is an exact copy of `automarker-template.py` except for
the implementation of `Automarker.run()`, which is tailored to the specific automarker's strategy.

In summary, each automarker implements the same overall algorithm:
1. it queries the API for all the exam students and questions
2. iterates over each student and each question
3. queries the API for the student's answers and marks and, for each question's section
4. calls `Automarker.run()` to compute the appropriate mark (suitably commented)
5. issues a POST request against the API to save the mark

**Each call to the `run()` method targets the marking of a specific section of the exam for a specific student.**

# How to use this repository

Start by cloning the repository. Then, using an up-to-date version of Python3, we recommend creating a virtual environment and installing the required dependencies (the examples provided assume a UNIX environment):
```shell
python3 -m venv venv
. venv/bin/activate
pip install -r requirements.txt
```

The preamble of every script (within `main()`) makes requests to the Answerbook API to fetch students, questions, answers and existing marks for the specified assessment.
Authentication happens via your Answerbook credentials, which need be entered as env vars in a dedicated `.env` file. You can generate the `.env` file from the template you find
in this repository, and update it with your credentials.

```shell
cp .env.template .env
```

For our local dev environment, we can use `adumble` as username and `pass` as password.

You can then implement your marker starting from `automarker-template.py` and replacing the body of the `run()` method within the `Automarker` class
with your own custom code. Every automarker script is invoked with one mandatory argument: the root URL of Answerbook API for the assessment. For the 2023-2024 12345 exam, for example, invoking the `no-answer-automarker.py` looks like:

```shell
python examples/no-answer-automarker.py https://answerbook-api.doc.ic.ac.uk/y2023_12345_exam
```

To run automarkers (e.g. the `no-answer-automarker`) locally against an instance of the API running in local host, the above currently becomes:

```shell
python examples/no-answer-automarker.py http://localhost:5004/y2023_12345_exam
```

## The `run()` method contract

### Parameters
The `run()` method accepts the following parameters:

| **Param name** | **Description**                                                                                                                                                                                          |
|----------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `username` | The student username                                                                                                                                                                                     |
| `section_id` | The ID of the section to mark. This is in the form of dash-separated digits e.g. 1-1-2 represents Question 1, Part a, Section ii.                                                                        |
| `max_mark` | The section's maximum mark.                                                                                                                                                                              |
| `tasks` | The section's tasks. See your live Answerbook instance API docs and [the wiki](https://github.com/the-answerbook-project/answerbook-api/wiki/Assessment-configuration:-keyword-reference) for reference. |

### Return value

The method is expected to return
- `None` for cases not matching the automarker's pre-conditions (a common one being the check for no existing mark for the section)
- a dictionary like `{"mark": int | float, "feedback": str}` for all other cases.
