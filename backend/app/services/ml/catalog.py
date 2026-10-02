"""Register exported, development-selected profiles with existing products."""
import json
import uuid
from pathlib import Path
from app.core.config import settings


def catalog() -> dict:
    path = Path(settings.ML_MODEL_ROOT) / 'catalog.json'
    return json.loads(path.read_text()) if path.is_file() else {}


def public_profiles() -> list[dict]:
    return [{key: value[key] for key in ('id', 'label', 'dataset', 'category', 'metrics')}
            for value in catalog().values()
            if (Path(settings.ML_MODEL_ROOT) / value['definition']['checkpoint']).is_file()]


def register_profile(product_id: str, profile_id: str) -> None:
    """Accept server-exported profile IDs, never client checkpoint paths."""
    definition = catalog().get(profile_id)
    if definition is None:
        raise ValueError('Trained profile not found. Refresh the available profiles.')
    root = Path(settings.ML_MODEL_ROOT).resolve()
    checkpoint = (root / definition['definition']['checkpoint']).resolve()
    if not checkpoint.is_relative_to(root) or not checkpoint.is_file():
        raise ValueError('Trained checkpoint is unavailable.')
    target = root / f'{uuid.UUID(product_id)}.json'
    temporary = target.with_name(target.name + f'.{uuid.uuid4().hex}.tmp')
    temporary.write_text(json.dumps(definition['definition'], indent=2) + '\n')
    temporary.replace(target)
