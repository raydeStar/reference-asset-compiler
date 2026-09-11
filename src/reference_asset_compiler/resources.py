"""Read the same adapter registry from a checkout or an installed wheel."""

from importlib.resources import files
import json
from pathlib import Path


def checkout_root() -> Path | None:
    root = Path(__file__).resolve().parents[2]
    if ((root / "pyproject.toml").is_file()
            and (root / "configs" / "model-adapters.json").is_file()
            and (root / "workflows" / "geometry").is_dir()):
        return root
    return None


def load_registry() -> dict:
    root = checkout_root()
    resource = (root / "configs" / "model-adapters.json" if root else
                files("reference_asset_compiler").joinpath("data", "model-adapters.json"))
    registry = json.loads(resource.read_text(encoding="utf-8"))
    if not isinstance(registry, dict) or not isinstance(registry.get("adapters"), list):
        raise ValueError("Adapter registry requires an adapters list")
    return registry
