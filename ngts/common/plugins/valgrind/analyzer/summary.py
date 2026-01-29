from __future__ import annotations

import dataclasses
import logging

from . import _text

logger = logging.getLogger(__name__)


@dataclasses.dataclass(frozen=True)
class DecisionConfig:
    definitely_threshold: int = dataclasses.field(default=0, metadata={"name": "Definitely Lost Threshold", "fmt": _text.to_readable})
    indirectly_threshold: int = dataclasses.field(default=0, metadata={"name": "Indirectly Lost Threshold", "fmt": _text.to_readable})
    possibly_threshold: int = dataclasses.field(default=0, metadata={"name": "Possibly Lost Threshold", "fmt": _text.to_readable})
    fail_on_warnings: bool = dataclasses.field(default=False, metadata={"name": "Fail On Warnings Flag"})

    def __str__(self) -> str:
        result = ""
        for field in dataclasses.fields(self):
            if field.metadata.get('name'):
                value = getattr(self, field.name)
                if formatter := field.metadata.get('fmt'):
                    value = formatter(value)
                result += f"{field.metadata['name']:<{_text.T_SPACE}}: {value}\n"
        return result.rstrip()

    @property
    def is_default_config(self) -> bool:
        for field in dataclasses.fields(self):
            if field.default != getattr(self, field.name):
                return False
        return True
