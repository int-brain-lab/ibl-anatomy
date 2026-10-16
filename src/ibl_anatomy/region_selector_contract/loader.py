"""Access the packaged region selector contract without filesystem assumptions."""

from __future__ import annotations

import json
from dataclasses import dataclass
from importlib.resources import files
from typing import Any


@dataclass(frozen=True)
class RegionSelectorContract:
    """Decoded shared selector traces and their schema and bundle manifest."""

    schema: dict[str, Any]
    traces: dict[str, Any]
    manifest: dict[str, Any]


def load_region_selector_contract() -> RegionSelectorContract:
    """Load v1 resources from this package, including when installed from a wheel."""
    root = files(__package__).joinpath("v1")
    return RegionSelectorContract(
        schema=json.loads(root.joinpath("schema.json").read_text(encoding="utf-8")),
        traces=json.loads(root.joinpath("traces.json").read_text(encoding="utf-8")),
        manifest=json.loads(root.joinpath("manifest.json").read_text(encoding="utf-8")),
    )
