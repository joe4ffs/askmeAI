import json
import re

from grader.providers.base import ImageInput


class FakeProvider:
    """Deterministic, network-free stand-in for a real model provider.

    Grades by simple keyword overlap between each rubric criterion and the student answer, and
    "OCRs" any image by returning a fixed placeholder transcription. Good enough to exercise the
    full pipeline (schema validation, CLI, eval script) without an API key; not a real grader or
    real OCR.
    """

    def complete(self, system: str, prompt: str, image: ImageInput | None = None) -> str:
        if image is not None:
            return json.dumps(
                {
                    "extracted_text": "[FakeProvider placeholder transcription — no real OCR performed]",
                    "confidence": "low",
                    "is_illegible": True,
                    "notes": "FakeProvider does not perform real OCR; set a real provider to transcribe images.",
                }
            )
        return self._fake_grade(prompt)

    def _fake_grade(self, prompt: str) -> str:
        rubric_items = re.findall(r"- \(([\d.]+) pts\) (.+)", prompt)
        student_match = re.search(r"Student answer:\n(.*?)\n\nGrade", prompt, re.DOTALL)
        student_answer = student_match.group(1).lower() if student_match else ""

        rubric_results = []
        total_score = 0.0
        total_possible = 0.0
        for points_str, criterion in rubric_items:
            points = float(points_str)
            total_possible += points
            keywords = [w for w in re.findall(r"[a-zA-Z]{4,}", criterion.lower())]
            overlap = sum(1 for w in keywords if w in student_answer)
            met = overlap >= max(1, len(keywords) // 2)
            awarded = points if met else 0.0
            total_score += awarded
            rubric_results.append(
                {
                    "criterion": criterion,
                    "status": "met" if met else "missed",
                    "points_awarded": awarded,
                    "points_possible": points,
                    "evidence": "FakeProvider keyword-overlap heuristic; not a real judgment.",
                }
            )

        return json.dumps(
            {
                "total_score": total_score,
                "total_possible": total_possible or 1.0,
                "rubric_results": rubric_results,
                "overall_rationale": "Graded by FakeProvider (keyword-overlap heuristic, not a real model).",
                "is_ambiguous": False,
                "ambiguity_reason": None,
                "corrected_answer": None,
            }
        )
