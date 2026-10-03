"""Safe validation and product binding for the external Member 1 bundle."""
import json
import uuid
from pathlib import Path

from app.core.config import settings
from app.services.ml.member1_worker.protocol import SUPPORTED_CATEGORIES

PROFILE_PREFIX = "member1/mvtec_ad/"


def member1_root() -> Path:
    return Path(settings.ML_M1_MODEL_ROOT).expanduser().resolve()


def member1_manifest() -> dict | None:
    root = member1_root()
    path = root / "model_manifest.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return None
    return data if isinstance(data, dict) else None


def member1_checkpoint(category: str) -> Path | None:
    if category not in SUPPORTED_CATEGORIES:
        return None
    manifest = member1_manifest()
    primary_model = manifest.get("primary_model") if manifest else None
    if not isinstance(primary_model, str) or primary_model.lower() != "patchcore":
        return None
    categories = manifest.get("supported_categories")
    if not isinstance(categories, list) or category not in categories:
        return None
    patchcore = manifest.get("patchcore")
    if not isinstance(patchcore, dict):
        return None
    model = patchcore.get(category)
    model_name = model.get("model") if isinstance(model, dict) else None
    if (not isinstance(model, dict)
            or not isinstance(model_name, str)
            or model_name.lower() != "patchcore"
            or model.get("backbone") != "wide_resnet50_2"):
        return None
    relative = model.get("checkpoint")
    expected = f"outputs/checkpoints/{category}/patchcore_{category}.ckpt"
    if relative != expected:
        return None
    root = member1_root()
    candidate = (root / relative).resolve()
    if not candidate.is_relative_to(root) or not candidate.is_file():
        return None
    return candidate


def available_member1_categories() -> list[str]:
    return [category for category in SUPPORTED_CATEGORIES if member1_checkpoint(category)]


def is_member1_definition(definition: dict) -> bool:
    return (definition.get("model") == "member1_patchcore"
            and definition.get("dataset") == "mvtec_ad"
            and definition.get("category") in SUPPORTED_CATEGORIES
            and member1_checkpoint(definition.get("category")) is not None)


def registered_member1_profiles() -> list[dict]:
    if not settings.ML_M1_ENABLED:
        return []
    return [
        {
            "id": f"{PROFILE_PREFIX}{category}",
            "label": f"{category.replace('_', ' ').title()} (Member 1 PatchCore)",
            "dataset": "mvtec_ad",
            "category": category,
            "metrics": {},
        }
        for category in available_member1_categories()
    ]


def register_member1_profile(product_id: str, profile_id: str) -> None:
    if not settings.ML_M1_ENABLED:
        raise ValueError("Member 1 profiles are disabled.")
    category = profile_id.removeprefix(PROFILE_PREFIX)
    if not profile_id.startswith(PROFILE_PREFIX) or category not in SUPPORTED_CATEGORIES:
        raise ValueError("Trained profile not found. Refresh the available profiles.")
    if member1_checkpoint(category) is None:
        raise ValueError("Member 1 checkpoint is unavailable.")
    # Product bindings share the existing ML_MODEL_ROOT UUID namespace. This
    # keeps a product on exactly one active profile when switching runtimes.
    root = Path(settings.ML_MODEL_ROOT).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    target = root / f"{uuid.UUID(product_id)}.json"
    definition = {
        "model": "member1_patchcore",
        "dataset": "mvtec_ad",
        "category": category,
    }
    temporary = target.with_name(target.name + f".{uuid.uuid4().hex}.tmp")
    temporary.write_text(json.dumps(definition, indent=2) + "\n", encoding="utf-8")
    temporary.replace(target)
