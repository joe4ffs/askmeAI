import json

import pytest

from grader.providers import get_provider
from grader.providers.fake_provider import FakeProvider
from grader.providers.base import ImageInput


def test_get_provider_explicit_fake():
    provider = get_provider("fake")
    assert isinstance(provider, FakeProvider)


def test_get_provider_unknown_name_raises():
    with pytest.raises(ValueError):
        get_provider("not_a_real_provider")


def test_get_provider_env_var_selects_fake(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("AI_GRADER_PROVIDER", "fake")
    assert isinstance(get_provider(), FakeProvider)


def test_get_provider_autodetects_fake_with_no_keys(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("AI_GRADER_PROVIDER", raising=False)
    assert isinstance(get_provider(), FakeProvider)


def test_fake_provider_grades_matching_answer_as_met():
    provider = FakeProvider()
    prompt = """Subject: geography

Question:
What is the capital of France?

Reference answer:
Paris

Rubric (total 1.0 points):
- (1.0 pts) Names the correct capital city

Student answer:
The capital city is Paris.

Grade the student answer against the rubric above. Return JSON matching this schema:
{}
"""
    result = json.loads(provider.complete(system="", prompt=prompt))
    assert result["rubric_results"][0]["status"] == "met"
    assert result["total_score"] == 1.0


def test_fake_provider_grades_missing_keywords_as_missed():
    provider = FakeProvider()
    prompt = """Subject: geography

Question:
What is the capital of France?

Reference answer:
Paris

Rubric (total 1.0 points):
- (1.0 pts) Names the correct capital city

Student answer:
I don't know.

Grade the student answer against the rubric above. Return JSON matching this schema:
{}
"""
    result = json.loads(provider.complete(system="", prompt=prompt))
    assert result["rubric_results"][0]["status"] == "missed"
    assert result["total_score"] == 0.0


def test_fake_provider_ocr_returns_placeholder():
    provider = FakeProvider()
    result = json.loads(
        provider.complete(system="", prompt="transcribe", image=ImageInput("image/png", "abc123"))
    )
    assert result["is_illegible"] is True
