import pytest
from pydantic import ValidationError

from grader.schema import GradingRequest, GradingResult, RubricItem, RubricItemResult, RubricItemStatus


def _make_item(points_awarded=1.0, points_possible=1.0, status=RubricItemStatus.MET):
    return RubricItemResult(
        criterion="Explains X correctly",
        status=status,
        points_awarded=points_awarded,
        points_possible=points_possible,
        evidence="Student wrote '...'",
    )


def test_valid_result_accepted():
    result = GradingResult(
        total_score=1.0,
        total_possible=1.0,
        rubric_results=[_make_item()],
        overall_rationale="Fully correct.",
        is_ambiguous=False,
    )
    assert result.total_score == 1.0


def test_ambiguous_without_reason_rejected():
    with pytest.raises(ValidationError):
        GradingResult(
            total_score=0.5,
            total_possible=1.0,
            rubric_results=[_make_item(0.5, 1.0, RubricItemStatus.PARTIALLY_MET)],
            overall_rationale="Unclear handwriting in the middle step.",
            is_ambiguous=True,
            ambiguity_reason=None,
        )


def test_ambiguous_with_reason_accepted():
    result = GradingResult(
        total_score=0.5,
        total_possible=1.0,
        rubric_results=[_make_item(0.5, 1.0, RubricItemStatus.PARTIALLY_MET)],
        overall_rationale="Unclear handwriting in the middle step.",
        is_ambiguous=True,
        ambiguity_reason="Can't tell if the exponent is 2 or 3.",
    )
    assert result.is_ambiguous


def test_points_awarded_cannot_exceed_possible():
    with pytest.raises(ValidationError):
        GradingResult(
            total_score=2.0,
            total_possible=1.0,
            rubric_results=[_make_item(points_awarded=2.0, points_possible=1.0)],
            overall_rationale="Bad case that should never validate.",
            is_ambiguous=False,
        )


def test_grading_request_requires_answer_or_image():
    with pytest.raises(ValidationError):
        GradingRequest(
            question="What is 2+2?",
            reference_answer="4",
            rubric=[RubricItem(criterion="States the correct sum", points=1.0)],
        )


def test_grading_request_accepts_image_path_without_text():
    req = GradingRequest(
        question="What is 2+2?",
        reference_answer="4",
        rubric=[RubricItem(criterion="States the correct sum", points=1.0)],
        student_answer_image_path="data/samples/answer1.png",
    )
    assert req.student_answer == ""
    assert req.student_answer_image_path == "data/samples/answer1.png"
