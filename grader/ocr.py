import base64
import json
import mimetypes
import os
from pathlib import Path

import anthropic

from grader.schema import OcrResult

MODEL = "claude-sonnet-5"

SYSTEM_PROMPT = """You are a careful transcriptionist. You are given an image of a handwritten \
student answer. You must:

1. Transcribe the handwritten text as accurately as possible, preserving the student's wording, \
math notation, and structure.
2. Set is_illegible=true whenever any part of the answer cannot be confidently read — do not guess \
at illegible words or silently skip them.
3. Set confidence to "high" only if you are confident in the entire transcription, "medium" if most \
of it is clear but some words are uncertain, "low" if significant portions are unclear.
4. Do not correct spelling, grammar, or factual errors in the transcription — transcribe exactly \
what is written, errors included.

Respond with ONLY a JSON object matching the required schema. No prose outside the JSON.
"""


def _image_to_data_url(path: str) -> tuple[str, str]:
    media_type, _ = mimetypes.guess_type(path)
    if media_type is None:
        raise ValueError(f"Could not determine image media type for {path!r}")
    data = base64.standard_b64encode(Path(path).read_bytes()).decode("utf-8")
    return media_type, data


def ocr_image(image_path: str, client: anthropic.Anthropic | None = None) -> OcrResult:
    client = client or anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    media_type, data = _image_to_data_url(image_path)

    response = client.messages.create(
        model=MODEL,
        max_tokens=2048,
        system=SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {"type": "base64", "media_type": media_type, "data": data},
                    },
                    {
                        "type": "text",
                        "text": f"Transcribe the handwritten answer in this image. Return JSON "
                        f"matching this schema:\n{json.dumps(OcrResult.model_json_schema(), indent=2)}",
                    },
                ],
            }
        ],
    )

    text = response.content[0].text
    return OcrResult.model_validate_json(_extract_json(text))


def _extract_json(text: str) -> str:
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"No JSON object found in model response: {text!r}")
    return text[start : end + 1]
