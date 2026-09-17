"""Run the script grader against a standing set of deliberately tricky test cases and report
how often it got fooled.

Unlike run_eval.py (which checks numeric agreement with a human-graded score), this checks
behavioral properties: did the grader catch a wrong-reasoning-right-answer trick, resist
keyword-stuffed nonsense, avoid rewarding confident-but-irrelevant answers, correctly accept a
valid-but-nonstandard method, and flag illegible input instead of confidently guessing.

Each case is rendered as a plain typed-text image (so it exercises the real vision pipeline used
by uploaded scripts, not a text-only shortcut) and graded via grade_script_input(). See
data/adversarial/case_001.json for the case format.

Usage:
    python scripts/run_adversarial_eval.py data/adversarial
    python scripts/run_adversarial_eval.py data/adversarial --out adversarial_results.csv
"""

import argparse
import base64
import io
import json
import sys
import time
from pathlib import Path

import pandas as pd
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from grader.providers import ImageInput
from grader.schema import AdversarialCase, ScriptGradingResult
from grader.script_grader import grade_script_input


def load_cases(eval_dir: Path) -> list[AdversarialCase]:
    return [
        AdversarialCase.model_validate(json.loads(path.read_text()))
        for path in sorted(eval_dir.glob("*.json"))
    ]


def render_case_image(case: AdversarialCase) -> ImageInput:
    """Render a case's question+answer as an image — a stand-in for a scanned script, so grading
    goes through the same vision path real uploads use. Plain typed text by default; if
    render_illegible is set, degraded (low contrast, jitter, noise) to simulate genuinely
    hard-to-read handwriting rather than clean-but-nonsensical text."""
    text = f"Q: {case.question}\n\nA: {case.student_answer}"
    lines = []
    for paragraph in text.split("\n"):
        while len(paragraph) > 80:
            lines.append(paragraph[:80])
            paragraph = paragraph[80:]
        lines.append(paragraph)

    width, line_height, padding = 700, 22, 20
    height = padding * 2 + line_height * len(lines)
    img = Image.new("RGB", (width, height), color="white")
    draw = ImageDraw.Draw(img)

    if case.render_illegible:
        import random

        rng = random.Random(case.case_id)  # deterministic jitter per case
        for i, line in enumerate(lines):
            base_y = padding + i * line_height
            for ch_idx, ch in enumerate(line):
                x = padding + ch_idx * 9 + rng.randint(-2, 2)
                y = base_y + rng.randint(-3, 3)
                gray = rng.randint(140, 200)  # low contrast against white
                draw.text((x, y), ch, fill=(gray, gray, gray))
        # overlay light noise speckles
        for _ in range(width * height // 40):
            x, y = rng.randint(0, width - 1), rng.randint(0, height - 1)
            draw.point((x, y), fill=(rng.randint(150, 220),) * 3)
    else:
        for i, line in enumerate(lines):
            draw.text((padding, padding + i * line_height), line, fill="black")

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return ImageInput(media_type="image/png", base64_data=base64.standard_b64encode(buf.getvalue()).decode("utf-8"))


def check_case(case: AdversarialCase, result: ScriptGradingResult) -> dict:
    """Behavioral check against the case's expectations. Matches by position — each case renders
    exactly one question, so it should be result.questions[0]."""
    row = {
        "case_id": case.case_id,
        "trap": case.trap.value,
        "subject": case.subject,
        "passed": None,
        "failure_reason": None,
    }
    if not result.questions:
        row["passed"] = False
        row["failure_reason"] = "grader returned zero questions for a one-question case"
        return row

    q = result.questions[0]
    failures = []
    if case.expect_correct is not None and q.is_correct != case.expect_correct:
        failures.append(
            f"expected is_correct={case.expect_correct}, got {q.is_correct}"
        )
    if case.expect_flagged is not None and q.needs_human_review != case.expect_flagged:
        failures.append(
            f"expected needs_human_review={case.expect_flagged}, got {q.needs_human_review}"
        )

    row["passed"] = len(failures) == 0
    row["failure_reason"] = "; ".join(failures) if failures else None
    row["actual_is_correct"] = q.is_correct
    row["actual_needs_human_review"] = q.needs_human_review
    row["actual_confidence"] = q.confidence.value
    return row


def run_adversarial_eval(eval_dir: Path, delay_seconds: float = 0) -> pd.DataFrame:
    rows = []
    cases = load_cases(eval_dir)
    for i, case in enumerate(cases):
        if i > 0 and delay_seconds:
            time.sleep(delay_seconds)
        image = render_case_image(case)
        try:
            result = grade_script_input(image, subject=case.subject)
        except Exception as exc:
            rows.append(
                {
                    "case_id": case.case_id,
                    "trap": case.trap.value,
                    "subject": case.subject,
                    "passed": False,
                    "failure_reason": f"grading error: {exc}",
                }
            )
            continue
        rows.append(check_case(case, result))
    return pd.DataFrame(rows)


def summarize(df: pd.DataFrame) -> str:
    if df.empty:
        return "No adversarial cases found."

    lines = [
        f"Cases run: {len(df)}",
        f"Passed: {df['passed'].sum()} / {len(df)} ({df['passed'].mean():.0%})",
        "",
        "By trap type:",
    ]
    for trap, group in df.groupby("trap"):
        lines.append(f"  {trap}: {group['passed'].sum()}/{len(group)} passed")

    failed = df[~df["passed"]]
    if not failed.empty:
        lines.append("\nFailures:")
        for _, row in failed.iterrows():
            lines.append(f"  {row['case_id']} ({row['trap']}): {row['failure_reason']}")

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("eval_dir", help="Directory of adversarial case JSON files")
    parser.add_argument("--out", help="Optional path to write per-case results as CSV")
    parser.add_argument(
        "--delay",
        type=float,
        default=0,
        help="Seconds to wait between cases (use e.g. 15 to stay under a free-tier rate limit)",
    )
    args = parser.parse_args()

    df = run_adversarial_eval(Path(args.eval_dir), delay_seconds=args.delay)
    print(summarize(df))

    if args.out:
        df.to_csv(args.out, index=False)
        print(f"\nPer-case results written to {args.out}")


if __name__ == "__main__":
    main()
