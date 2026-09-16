from enum import Enum
from pydantic import BaseModel, Field, model_validator


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


class GradingRequest(BaseModel):
    question: str
    reference_answer: str
    rubric: list[RubricItem]
    student_answer: str
    subject: str = "general"
