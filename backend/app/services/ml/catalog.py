"""Register exported, development-selected profiles with existing products."""
import json
import uuid
from pathlib import Path
from app.core.config import settings


def catalog() -> dict:
    path = Path(settings.ML_MODEL_ROOT) / 'catalog.json'
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError, TypeError):
        return {}
    return data if isinstance(data, dict) else {}


def public_profiles() -> list[dict]:
    member2 = []
    root = Path(settings.ML_MODEL_ROOT).resolve()
    for value in catalog().values():
        try:
            checkpoint = (root / value['definition']['checkpoint']).resolve()
            if checkpoint.is_relative_to(root) and checkpoint.is_file():
                member2.append({key: value[key] for key in ('id', 'label', 'dataset', 'category', 'metrics')})
        except (KeyError, TypeError, ValueError):
            continue
    from app.services.ml.member1_artifacts import registered_member1_profiles
    return member2 + registered_member1_profiles()


def register_profile(product_id: str, profile_id: str) -> None:
    """Accept server-exported profile IDs, never client checkpoint paths."""
    if profile_id.startswith('member1/'):
        from app.services.ml.member1_artifacts import register_member1_profile
        register_member1_profile(product_id, profile_id)
        return
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
