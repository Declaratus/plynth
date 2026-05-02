from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from plynth.models.instance import InstanceConfig
from plynth.models.template import TemplateDefinition

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def minimal_template_path() -> Path:
    return FIXTURES_DIR / "minimal-template.yaml"


@pytest.fixture
def minimal_instance_path() -> Path:
    return FIXTURES_DIR / "minimal-instance.yaml"


@pytest.fixture
def minimal_template(minimal_template_path: Path) -> TemplateDefinition:
    with open(minimal_template_path, encoding="utf-8") as f:
        return TemplateDefinition.model_validate(yaml.safe_load(f))


@pytest.fixture
def minimal_instance(minimal_instance_path: Path) -> InstanceConfig:
    with open(minimal_instance_path, encoding="utf-8") as f:
        return InstanceConfig.model_validate(yaml.safe_load(f))
