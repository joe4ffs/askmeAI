from grader.presets import load_preset
from grader.schema import SubjectPreset


def test_load_preset_returns_none_for_unknown_subject(tmp_path):
    assert load_preset("nonexistent_subject", presets_dir=tmp_path) is None


def test_load_preset_reads_matching_file(tmp_path):
    (tmp_path / "chemistry.json").write_text(
        '{"subject": "chemistry", "grading_instructions": "Accept balanced equations in any valid form."}'
    )

    preset = load_preset("chemistry", presets_dir=tmp_path)

    assert preset == SubjectPreset(
        subject="chemistry", grading_instructions="Accept balanced equations in any valid form."
    )


def test_bundled_math_preset_loads():
    preset = load_preset("math")
    assert preset is not None
    assert preset.subject == "math"
    assert "partial credit" in preset.grading_instructions.lower()


def test_bundled_english_preset_loads():
    preset = load_preset("english")
    assert preset is not None
    assert preset.subject == "english"


def test_bundled_operating_systems_preset_loads():
    preset = load_preset("operating_systems")
    assert preset is not None
    assert preset.subject == "operating_systems"
