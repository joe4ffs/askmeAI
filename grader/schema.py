from enum import Enum
from pydantic import BaseModel, Field, model_validator


class OcrConfidence(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class OcrResult(BaseModel):
    extracted_text: str = Field(description="The transcribed text of the handwritten answer")
    confidence: OcrConfidence
    is_illegible: bool = Field(
        description="True if part or all of the answer could not be confidently transcribed"
    )
    notes: str | None = Field(
        default=None,
        description="Explanation of what's illegible or uncertain; required if is_illegible is True",
    )

    @model_validator(mode="after")
    def _illegible_requires_notes(self) -> "OcrResult":
        if self.is_illegible and not self.notes:
            raise ValueError("notes is required when is_illegible is True")
        return self


class RubricItemStatus(str, Enum):
    MET = "met"
    PARTIALLY_MET = "partially_met"
    MISSED = "missed"
    NOT_APPLICABLE = "not_applicable"


class RubricItemResult(BaseModel):
    criterion: str = Field(description="The rubric criterion being judged, verbatim from the rubric")
    status: RubricItemStatus
    points_awarded: float = Field(ge=0)
    points_possible: float = Field(gt=0)
    evidence: str = Field(description="Quote or paraphrase from the student answer supporting this judgment")


class GradingResult(BaseModel):
    total_score: float = Field(ge=0)
    total_possible: float = Field(gt=0)
    rubric_results: list[RubricItemResult]
    overall_rationale: str = Field(description="Short summary of why this score was given")
    is_ambiguous: bool = Field(
        description="True if the answer is genuinely unclear/contradictory and a human should review it"
    )
    ambiguity_reason: str | None = Field(
        default=None, description="Required if is_ambiguous is True; explains what's unclear"
    )
    corrected_answer: str | None = Field(
        default=None,
        description="If the student's answer had a fixable error, a corrected version of the key parts; "
        "otherwise None",
    )

    @model_validator(mode="after")
    def _ambiguity_requires_reason(self) -> "GradingResult":
        if self.is_ambiguous and not self.ambiguity_reason:
            raise ValueError("ambiguity_reason is required when is_ambiguous is True")
        return self

    @model_validator(mode="after")
    def _points_within_bounds(self) -> "GradingResult":
        for item in self.rubric_results:
            if item.points_awarded > item.points_possible:
                raise ValueError(
                    f"points_awarded ({item.points_awarded}) exceeds points_possible "
                    f"({item.points_possible}) for criterion {item.criterion!r}"
                )
        return self


class RubricItem(BaseModel):
    criterion: str
    points: float = Field(gt=0)


class SubjectPreset(BaseModel):
    subject: str
    grading_instructions: str = Field(
        description="Subject-specific grading guidance appended to the engine's system prompt"
    )


class GradingRequest(BaseModel):
    question: str
    reference_answer: str
    rubric: list[RubricItem]
    student_answer: str = ""
    student_answer_image_path: str | None = Field(
        default=None,
        description="Path to a handwritten answer image; if set and student_answer is empty, "
        "grade_file.py OCRs this image first to fill student_answer",
    )
    subject: str = "general"

    @model_validator(mode="after")
    def _answer_or_image_required(self) -> "GradingRequest":
        if not self.student_answer and not self.student_answer_image_path:
            raise ValueError("either student_answer or student_answer_image_path is required")
        return self


class ScriptQuestionResult(BaseModel):
    question_text: str = Field(description="The question as found in the script, verbatim or paraphrased")
    student_answer_as_written: str = Field(description="The student's answer to this question, transcribed")
    is_correct: bool
    explanation: str = Field(description="Why the answer is correct or incorrect")
    correction: str | None = Field(
        default=None, description="The correct answer/fix, if is_correct is False; otherwise None"
    )
    concept: str = Field(
        description="Short tag (2-5 words) for the underlying concept this question tests, e.g. "
        "'quadratic factoring' or 'thread synchronization' — used to track recurring weak areas"
    )


class ScriptGradingResult(BaseModel):
    questions: list[ScriptQuestionResult]
    overall_summary: str = Field(description="Short summary of overall performance across the script")
    score_estimate: str = Field(description="e.g. '7/10 questions correct' — a rough tally, not a rubric score")


class HumanRubricJudgment(BaseModel):
    criterion: str = Field(description="The rubric criterion being judged, verbatim from the rubric")
    status: RubricItemStatus
    points_awarded: float = Field(ge=0)
    points_possible: float = Field(gt=0)

    @model_validator(mode="after")
    def _points_within_bounds(self) -> "HumanRubricJudgment":
        if self.points_awarded > self.points_possible:
            raise ValueError(
                f"points_awarded ({self.points_awarded}) exceeds points_possible "
                f"({self.points_possible}) for criterion {self.criterion!r}"
            )
        return self


class EvalCase(BaseModel):
    case_id: str
    request: GradingRequest
    human_judgments: list[HumanRubricJudgment]

    @property
    def human_total_score(self) -> float:
        return sum(j.points_awarded for j in self.human_judgments)
