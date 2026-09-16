import json
from unittest.mock import MagicMock

from grader.engine import grade, _extract_json
from grader.schema import GradingRequest, RubricItem


def _fake_response(payload: dict) -> MagicMock:
    response = MagicMock()
    response.content = [MagicMock(text=json.dumps(payload))]
    return response


def test_extract_json_strips_surrounding_prose():
    text = "Here is the result:\n{\"a\": 1}\nHope that helps!"
    assert _extract_json(text) == '{"a": 1}'


def test_grade_calls_model_and_parses_result():
    req = GradingRequest(
        question="What is the capital of France?",
        reference_answer="Paris",
        rubric=[RubricItem(criterion="Names the correct capital city", points=1.0)],
        student_answer="Paris",
        subject="geography",
    )

    payload = {
        "total_score": 1.0,
        "total_possible": 1.0,
        "rubric_results": [
            {
                "criterion": "Names the correct capital city",
                "status": "met",
                "points_awarded": 1.0,
                "points_possible": 1.0,
                "evidence": "Student wrote 'Paris'",
            }
        ],
        "overall_rationale": "Correct.",
        "is_ambiguous": False,
        "ambiguity_reason": None,
        "corrected_answer": None,
    }

    client = MagicMock()
    client.messages.create.return_value = _fake_response(payload)

    result = grade(req, client=client)

    assert result.total_score == 1.0
    assert result.rubric_results[0].status == "met"
    client.messages.create.assert_called_once()


def test_grade_appends_subject_preset_to_system_prompt():
    req = GradingRequest(
        question="Solve for x: 2x = 4",
        reference_answer="x = 2",
        rubric=[RubricItem(criterion="States x = 2", points=1.0)],
        student_answer="x = 2",
        subject="math",
    )

    payload = {
        "total_score": 1.0,
        "total_possible": 1.0,
        "rubric_results": [
            {
                "criterion": "States x = 2",
                "status": "met",
                "points_awarded": 1.0,
                "points_possible": 1.0,
                "evidence": "Student wrote 'x = 2'",
            }
        ],
        "overall_rationale": "Correct.",
        "is_ambiguous": False,
        "ambiguity_reason": None,
        "corrected_answer": None,
    }

    client = MagicMock()
    client.messages.create.return_value = _fake_response(payload)

    grade(req, client=client)

    system_prompt = client.messages.create.call_args.kwargs["system"]
    assert "partial credit" in system_prompt.lower()


def test_grade_uses_base_prompt_for_subject_without_preset():
    req = GradingRequest(
        question="What is the capital of France?",
        reference_answer="Paris",
        rubric=[RubricItem(criterion="Names the correct capital city", points=1.0)],
        student_answer="Paris",
        subject="geography",
    )

    payload = {
        "total_score": 1.0,
        "total_possible": 1.0,
        "rubric_results": [
            {
                "criterion": "Names the correct capital city",
                "status": "met",
                "points_awarded": 1.0,
                "points_possible": 1.0,
                "evidence": "Student wrote 'Paris'",
            }
        ],
        "overall_rationale": "Correct.",
        "is_ambiguous": False,
        "ambiguity_reason": None,
        "corrected_answer": None,
    }

    client = MagicMock()
    client.messages.create.return_value = _fake_response(payload)

    grade(req, client=client)

    system_prompt = client.messages.create.call_args.kwargs["system"]
    assert "Subject-specific guidance" not in system_prompt
