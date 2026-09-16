import json
import os

import anthropic

from grader.schema import GradingRequest, GradingResult

MODEL = "claude-sonnet-5"

SYSTEM_PROMPT = """You are a strict, fair grading assistant. You grade a student's answer against a \
given rubric and reference answer. You must:

1. Judge each rubric criterion independently — met, partially_met, missed, or not_applicable.
2. Award points per criterion that never exceed that criterion's points_possible, and never award \
partial credit without a specific reason in `evidence`.
3. Base every judgment only on what the student actually wrote — never assume intent that isn't on the page.
4. Set is_ambiguous=true whenever the answer is illegible, self-contradictory, or could reasonably be \
graded two different ways — do not silently pick one interpretation and hide the uncertainty.
5. Only fill corrected_answer when there is a concrete, fixable error (e.g. an arithmetic slip, a \
mislabeled formula) — do not rewrite answers that are already correct or that are wrong for reasons \
you're not confident about.

Respond with ONLY a JSON object matching the required schema. No prose outside the JSON.
"""


def _build_user_prompt(req: GradingRequest) -> str:
    rubric_lines = "\n".join(f"- ({item.points} pts) {item.criterion}" for item in req.rubric)
    total_possible = sum(item.points for item in req.rubric)
    return f"""Subject: {req.subject}

Question:
{req.question}

Reference answer:
{req.reference_answer}

Rubric (total {total_possible} points):
{rubric_lines}

Student answer:
{req.student_answer}

Grade the student answer against the rubric above. Return JSON matching this schema:
{json.dumps(GradingResult.model_json_schema(), indent=2)}
"""


def grade(req: GradingRequest, client: anthropic.Anthropic | None = None) -> GradingResult:
    client = client or anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    response = client.messages.create(
        model=MODEL,
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": _build_user_prompt(req)}],
    )

    text = response.content[0].text
    return GradingResult.model_validate_json(_extract_json(text))


def _extract_json(text: str) -> str:
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"No JSON object found in model response: {text!r}")
    return text[start : end + 1]
