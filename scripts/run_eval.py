"""Run the grading engine over a directory of human-graded eval cases and report agreement.

Eval case file format — see data/eval/case_001.json:
{
  "case_id": "case_001",
  "request": { ...GradingRequest fields... },
  "human_judgments": [
    {"criterion": "...", "status": "met", "points_awarded": 2, "points_possible": 2}, ...
  ]
}

Usage:
    python scripts/run_eval.py data/eval
    python scripts/run_eval.py data/eval --out results.csv
"""

import argparse
import json
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from grader.engine import grade
from grader.schema import EvalCase


def load_eval_cases(eval_dir: Path) -> list[EvalCase]:
    return [
        EvalCase.model_validate(json.loads(path.read_text()))
        for path in sorted(eval_dir.glob("*.json"))
    ]


def run_eval(eval_dir: Path, delay_seconds: float = 0) -> pd.DataFrame:
    rows = []
    cases = load_eval_cases(eval_dir)
    for i, case in enumerate(cases):
        if i > 0 and delay_seconds:
            time.sleep(delay_seconds)
        try:
            result = grade(case.request)
        except Exception as exc:
            print(f"skipping {case.case_id}: {exc}", file=sys.stderr)
            continue
        rows.append(
            {
                "case_id": case.case_id,
                "subject": case.request.subject,
                "model_score": result.total_score,
                "human_score": case.human_total_score,
                "total_possible": result.total_possible,
                "abs_diff": abs(result.total_score - case.human_total_score),
                "is_ambiguous": result.is_ambiguous,
            }
        )
    return pd.DataFrame(rows)


def summarize(df: pd.DataFrame) -> str:
    if df.empty:
        return "No eval cases found."

    exact_agreement = (df["abs_diff"] == 0).mean()
    near_agreement = (df["abs_diff"] <= 0.1 * df["total_possible"]).mean()
    mae = df["abs_diff"].mean()

    lines = [
        f"Cases evaluated: {len(df)}",
        f"Mean absolute error: {mae:.2f} points",
        f"Exact agreement: {exact_agreement:.0%}",
        f"Near agreement (within 10% of total): {near_agreement:.0%}",
        f"Flagged ambiguous by model: {df['is_ambiguous'].sum()}",
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("eval_dir", help="Directory of eval case JSON files")
    parser.add_argument("--out", help="Optional path to write per-case results as CSV")
    parser.add_argument(
        "--delay",
        type=float,
        default=0,
        help="Seconds to wait between cases (use e.g. 15 to stay under a free-tier rate limit)",
    )
    args = parser.parse_args()

    df = run_eval(Path(args.eval_dir), delay_seconds=args.delay)
    print(summarize(df))

    if args.out:
        df.to_csv(args.out, index=False)
        print(f"\nPer-case results written to {args.out}")


if __name__ == "__main__":
    main()
