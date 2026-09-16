"""Grade a single student answer from a JSON case file.

Case file format:
{
  "question": "...",
  "reference_answer": "...",
  "rubric": [{"criterion": "...", "points": 1.0}, ...],
  "student_answer": "...",
  "subject": "physics"
}

Usage:
    python scripts/grade_file.py data/samples/case1.json
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from grader.engine import grade
from grader.schema import GradingRequest


def main(path: str) -> None:
    raw = json.loads(Path(path).read_text())
    req = GradingRequest.model_validate(raw)
    result = grade(req)
    print(result.model_dump_json(indent=2))


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python scripts/grade_file.py <case.json>", file=sys.stderr)
        sys.exit(1)
    main(sys.argv[1])
