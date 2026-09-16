import os

import anthropic

from grader.providers.base import ImageInput

MODEL = "claude-sonnet-5"


class AnthropicProvider:
    def __init__(self, client: anthropic.Anthropic | None = None, model: str = MODEL):
        self._client = client or anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        self._model = model

    def complete(self, system: str, prompt: str, image: ImageInput | None = None) -> str:
        content: str | list[dict] = prompt
        if image is not None:
            content = [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": image.media_type,
                        "data": image.base64_data,
                    },
                },
                {"type": "text", "text": prompt},
            ]

        response = self._client.messages.create(
            model=self._model,
            max_tokens=4096,
            system=system,
            messages=[{"role": "user", "content": content}],
        )
        return response.content[0].text
