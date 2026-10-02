"""Fair, saved-profile evaluation. Never fit or retune on the test set."""
import csv
import hashlib
import json
import platform
import random
from pathlib import Path
import numpy as np
from app.services.ml.shared.data import load_manifest, test_samples
from app.services.ml.shared.metrics import evaluate
from app.services.ml.shared.preprocessing import read_mask

METRICS = ('accuracy', 'balanced_accuracy', 'image_auroc', 'pixel_auroc', 'f2', 'f1', 'precision', 'recall',
           'false_accept_rate', 'false_reject_rate', 'latency_ms')


def provenance(document: dict, config) -> dict:
    return {"manifest_sha256": hashlib.sha256(json.dumps(document, sort_keys=True).encode()).hexdigest(),
            "preprocessing": {"image_size": config.image_size, "resize": "bilinear", "color": "RGB",
                              "crop": None, "input_range": [0, 1]},
            "shots": document['shots']}


def write_csv(path: Path, rows: list[dict], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=columns, extrasaction='ignore')
        writer.writeheader(); writer.writerows(rows)


def run_comparison(root: Path, manifest: Path, models: dict, output: Path,
                   config, *, patchcore_reason: str = 'Member 1 adapter/checkpoint not supplied') -> dict:
    document, _, _ = load_manifest(root, manifest)
    expected = provenance(document, config)
    category = document['category']
    samples = test_samples(root, category)
    selected = set()
    rng = random.Random(config.seed)
    for label in (0, 1):
        candidates = [p for p, y, _ in samples if y == label]
        selected.update(rng.sample(candidates, min(5, len(candidates))))
    examples = [p.relative_to(root/category).as_posix() for p in sorted(selected)]
    rows, predictions = [], []
    for name in ('autoencoder', 'padim', 'patchcore'):
        model = models.get(name)
        if model is None:
            reason = patchcore_reason if name == 'patchcore' else 'Checkpoint not supplied'
            rows.append({"model": name, "category": category, "status": "unavailable",
                         **dict.fromkeys(METRICS), "unavailable": {key: reason for key in METRICS}})
            continue
        if model.name != name or model.category != category or model.provenance != expected:
            raise ValueError(f"{name}: category, shared subset or preprocessing mismatch")
        if model.config.image_size != config.image_size or model.config.device != config.device:
            raise ValueError(f"{name}: preprocessing/device mismatch")
        if name == 'padim' and not model.pretrained:
            raise ValueError('Comparison requires a pretrained PaDiM backbone')
        # One unmeasured warm-up on this same device, then identical sequential test order.
        model.predict(samples[0][0])
        labels, scores, latencies, masks, maps = [], [], [], [], []
        for path, label, mask_path in samples:
            relative = path.relative_to(root/category).as_posix()
            heatmap = (output/'comparison/examples'/category/name/
                       path.parent.name/f'{path.stem}.png') if path in selected else None
            result, anomaly_map = model.predict(path, heatmap)
            predictions.append({**result.to_dict(), 'filename': relative, 'ground_truth': label})
            labels.append(label); scores.append(result.anomaly_score); latencies.append(result.latency_ms)
            masks.append(read_mask(mask_path, config.image_size) if mask_path else
                         np.zeros((config.image_size, config.image_size), dtype=bool) if label == 0 else None)
            maps.append(anomaly_map)
        metrics = evaluate(labels, scores, model.threshold, latencies, masks, maps)
        rows.append({'model': name, 'category': category, 'status': 'evaluated',
                     'threshold': model.threshold, **metrics})
    output.mkdir(parents=True, exist_ok=True)
    columns = ['model', 'category', *METRICS, 'threshold', 'status']
    write_csv(output/'metrics'/category/'comparison.csv', rows, columns)
    for row in rows:
        write_csv(output/'metrics'/category/f"{row['model']}.csv", [row], columns)
    write_csv(output/'comparison'/category/'predictions.csv', predictions,
              ['dataset','category','model','filename','ground_truth','anomaly_score','threshold',
               'verdict','heatmap_path','latency_ms'])
    report = {'dataset': 'mvtec_ad', 'category': category, 'provenance': expected,
              'seed': config.seed, 'hardware': {'platform': platform.platform(),
              'processor': platform.processor(), 'device': config.device},
              'latency_scope': 'shared image decode/resize + model inference; excludes output writes; one warmup',
              'test_files': [p.relative_to(root/category).as_posix() for p, _, _ in samples],
              'examples': examples, 'results': rows, 'predictions': predictions}
    destination = output/'comparison'/category
    destination.mkdir(parents=True, exist_ok=True)
    (destination/'results.json').write_text(json.dumps(report, indent=2, allow_nan=False)+'\n')
    (destination/'summary.json').write_text(json.dumps({'category': category, 'series': rows},
                                                       indent=2, allow_nan=False)+'\n')
    return report


def aggregate_reports(output: Path) -> None:
    reports = [json.loads(p.read_text()) for p in sorted((output/'comparison').glob('*/results.json'))]
    rows = [row for report in reports for row in report['results']]
    write_csv(output/'metrics/comparison.csv', rows, ['model','category',*METRICS,'threshold','status'])
    (output/'comparison/results.json').write_text(json.dumps(reports,indent=2,allow_nan=False)+'\n')
    (output/'comparison/summary.json').write_text(json.dumps({'series': rows},indent=2,allow_nan=False)+'\n')
