import json
from unittest.mock import patch

import pytest

from grader.schema import GradingResult, RubricItemResult, RubricItemStatus
from scripts.run_eval import load_eval_cases, run_eval, summarize


EVAL_CASE = {
    "case_id": "case_001",
    "request": {
        "subject": "geography",
        "question": "What is the capital of France?",
        "reference_answer": "Paris",
        "rubric": [{"criterion": "Names the correct capital city", "points": 1.0}],
        "student_answer": "Paris",
    },
    "human_judgments": [
        {
            "criterion": "Names the correct capital city",
            "status": "met",
            "points_awarded": 1.0,
            "points_possible": 1.0,
        }
    ],
}


def _write_case(tmp_path, name, data):
    (tmp_path / name).write_text(json.dumps(data))


def test_load_eval_cases_reads_directory(tmp_path):
    _write_case(tmp_path, "case_001.json", EVAL_CASE)

    cases = load_eval_cases(tmp_path)

    assert len(cases) == 1
    assert cases[0].case_id == "case_001"
    assert cases[0].human_total_score == 1.0


def _fake_grading_result(total_score: float) -> GradingResult:
    return GradingResult(
        total_score=total_score,
        total_possible=1.0,
        rubric_results=[
            RubricItemResult(
                criterion="Names the correct capital city",
                status=RubricItemStatus.MET,
                points_awarded=total_score,
                points_possible=1.0,
                evidence="Student wrote 'Paris'",
            )
        ],
        overall_rationale="Correct.",
        is_ambiguous=False,
    )


def test_run_eval_computes_diff_against_human_score(tmp_path):
    _write_case(tmp_path, "case_001.json", EVAL_CASE)

    with patch("scripts.run_eval.grade", return_value=_fake_grading_result(1.0)):
        df = run_eval(tmp_path)

    assert len(df) == 1
    assert df.iloc[0]["model_score"] == 1.0
    assert df.iloc[0]["human_score"] == 1.0
    assert df.iloc[0]["abs_diff"] == 0.0


def test_run_eval_flags_disagreement(tmp_path):
    _write_case(tmp_path, "case_001.json", EVAL_CASE)

    with patch("scripts.run_eval.grade", return_value=_fake_grading_result(0.0)):
        df = run_eval(tmp_path)

    assert df.iloc[0]["abs_diff"] == 1.0


def test_summarize_empty_dataframe():
    import pandas as pd

    assert summarize(pd.DataFrame()) == "No eval cases found."


def test_summarize_reports_exact_agreement(tmp_path):
    _write_case(tmp_path, "case_001.json", EVAL_CASE)

    with patch("scripts.run_eval.grade", return_value=_fake_grading_result(1.0)):
        df = run_eval(tmp_path)

    summary = summarize(df)
    assert "Exact agreement: 100%" in summary
