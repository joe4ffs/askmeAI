import json
from pathlib import Path

from grader.schema import SubjectPreset

PRESETS_DIR = Path(__file__).resolve().parent.parent / "presets"


def load_preset(subject: str, presets_dir: Path = PRESETS_DIR) -> SubjectPreset | None:
    path = presets_dir / f"{subject}.json"
    if not path.exists():
        return None
    return SubjectPreset.model_validate(json.loads(path.read_text()))
