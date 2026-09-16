import json
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from grader.ocr import ocr_image, _extract_json
from grader.schema import OcrResult, OcrConfidence


def _fake_response(payload: dict) -> MagicMock:
    response = MagicMock()
    response.content = [MagicMock(text=json.dumps(payload))]
    return response


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

    client = MagicMock()
    client.messages.create.return_value = _fake_response(payload)

    result = ocr_image(str(image_path), client=client)

    assert result.extracted_text == "A process has its own memory."
    assert result.confidence == OcrConfidence.HIGH
    client.messages.create.assert_called_once()

    call_kwargs = client.messages.create.call_args.kwargs
    content = call_kwargs["messages"][0]["content"]
    assert content[0]["type"] == "image"
    assert content[0]["source"]["media_type"] == "image/png"


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
