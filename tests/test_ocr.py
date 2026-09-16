import json
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from grader.ocr import ocr_image, _extract_json
from grader.schema import OcrResult, OcrConfidence


def _fake_provider(payload: dict) -> MagicMock:
    provider = MagicMock()
    provider.complete.return_value = json.dumps(payload)
    return provider


def test_extract_json_strips_surrounding_prose():
    text = "Sure, here's the transcription:\n{\"a\": 1}\nLet me know if you need more."
    assert _extract_json(text) == '{"a": 1}'


def test_ocr_image_calls_model_and_parses_result(tmp_path):
    image_path = tmp_path / "answer.png"
    image_path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"fake image data")

    payload = {
        "extracted_text": "A process has its own memory.",
        "confidence": "high",
        "is_illegible": False,
        "notes": None,
    }

    provider = _fake_provider(payload)

    result = ocr_image(str(image_path), provider=provider)

    assert result.extracted_text == "A process has its own memory."
    assert result.confidence == OcrConfidence.HIGH
    provider.complete.assert_called_once()

    call_kwargs = provider.complete.call_args.kwargs
    assert call_kwargs["image"].media_type == "image/png"


def test_illegible_without_notes_rejected():
    with pytest.raises(ValidationError):
        OcrResult(
            extracted_text="unclear",
            confidence=OcrConfidence.LOW,
            is_illegible=True,
            notes=None,
        )


def test_illegible_with_notes_accepted():
    result = OcrResult(
        extracted_text="unclear middle section",
        confidence=OcrConfidence.LOW,
        is_illegible=True,
        notes="Cannot tell if the exponent is 2 or 3.",
    )
    assert result.is_illegible
