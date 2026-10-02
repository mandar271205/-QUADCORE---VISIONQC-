"""Read-only real experiment summaries and bounded example-image access."""
import json
from pathlib import Path
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from app.core.config import settings

router = APIRouter()
METRICS = ('accuracy', 'balanced_accuracy', 'f2', 'f1', 'precision', 'recall',
           'image_auroc', 'pixel_auroc', 'false_accept_rate', 'false_reject_rate', 'latency_ms')


@router.get('/comparison')
async def comparison(request: Request):
    root = Path(settings.ML_EXPERIMENT_ROOT) / '30shot_f2'
    path = root / 'results.json'
    if not path.is_file():
        return {'state': 'pending', 'shots': 30, 'results': []}
    rows = json.loads(path.read_text())
    result = []
    for row in rows:
        folder = root / row['category'] / row['model'] / 'examples'
        examples = []
        for image in sorted(folder.rglob('*_overlay.png')):
            relative = image.relative_to(root).as_posix()
            examples.append({'label': 'GOOD' if image.parent.name == 'good' else 'DEFECT',
                             'filename': image.stem.removesuffix('_overlay'),
                             'url': str(request.url_for('comparison_example', relative_path=relative))})
        result.append({key: row.get(key) for key in ('dataset', 'category', 'model', *METRICS)} | {'examples': examples})
    return {'state': 'complete' if len(rows) == 9 else 'partial', 'shots': 30,
            'protocol': 'Same 30 normal training images and frozen test list per category; development F2 selects thresholds.',
            'results': result}


@router.get('/examples/{relative_path:path}', name='comparison_example')
async def comparison_example(relative_path: str):
    root = (Path(settings.ML_EXPERIMENT_ROOT) / '30shot_f2').resolve()
    target = (root / relative_path).resolve()
    if not target.is_relative_to(root) or 'examples' not in target.relative_to(root).parts or target.suffix != '.png' or not target.is_file():
        raise HTTPException(404, 'Example image not found.')
    return FileResponse(target, media_type='image/png')
