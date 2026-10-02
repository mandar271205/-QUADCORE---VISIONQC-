"""Resumable development-only single/fusion search; never rank on final labels."""
import argparse
import fcntl
import itertools
import json
from pathlib import Path
import numpy as np
from app.services.ml.factory import model_class
from app.services.ml.ensemble import EnsembleBaseline
from app.services.ml.shared.metrics import evaluate
from app.services.ml.shared.result import normalize_score
from train_suite import choose_threshold, score_samples, release

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'outputs/improved_f2'


def rank(metrics):
    return metrics['f2'], metrics['accuracy'], metrics['image_auroc'] or 0


def run(report_path, device):
    source = json.loads(report_path.read_text())
    dataset, category = source['dataset'], source['category']
    folder = OUT / dataset / category
    folder.mkdir(parents=True, exist_ok=True)
    if (folder / 'results.json').exists():
        return
    base = ROOT / 'data' / dataset / category
    split = json.loads((report_path.parent / 'split.json').read_text())
    labels = [item['label'] for item in split['development']]
    extended=ROOT/'outputs/refined_f2'/dataset/category/'validation_trials.json'
    if extended.exists():source['trials'].extend(json.loads(extended.read_text()))
    prior_selection=next(r for r in source['final_results'] if r['selected_for_deployment'])
    prior=next(t for t in source['trials'] if t['model']==prior_selection['model'] and t['parameters']==prior_selection['parameters'])
    other=[t for t in source['trials'] if t['model']=='patchcore' and t['checkpoint']!=prior['checkpoint']]
    candidates = [prior] + sorted(other,key=lambda t: rank(t['validation']),reverse=True)[:1]
    padim = [t for t in source['trials'] if t['model'] == 'padim']
    if padim:
        candidate=max(padim,key=lambda t: rank(t['validation']))
        if candidate['checkpoint']!=prior['checkpoint']:candidates.append(candidate)
    models, normal, scores = [], [], []
    trials = []
    # Preserve the prior model on a development tie, including its threshold.
    baseline={'members':[prior['checkpoint']],'member_models':[prior['model']],
              'weights':[1.0],'threshold':.5,'validation':prior['validation'],'threshold_trials':[]}
    best = ((*rank(prior['validation']),-1),(0,),[1.0],.5,baseline)
    try:
        for candidate in candidates:
            model = model_class(candidate['model']).load(ROOT / candidate['checkpoint'], device)
            models.append(model)
            normal.append([normalize_score(model.predict(base / item['filename'])[0].anomaly_score, model.threshold)
                           for item in split['calibration']])
            scores.append([normalize_score(model.predict(base / item['filename'])[0].anomaly_score, model.threshold)
                           for item in split['development']])
        for count in (1, 2):
            for indices in itertools.combinations(range(len(models)), count):
                weight_sets = [[1.0]] if count == 1 else [[.25, .75], [.5, .5], [.75, .25]]
                for weights in weight_sets:
                    dev = np.sum([np.asarray(scores[i]) * w for i, w in zip(indices, weights)], axis=0)
                    cal = np.sum([np.asarray(normal[i]) * w for i, w in zip(indices, weights)], axis=0)
                    threshold, _, threshold_trials = choose_threshold(cal, labels, dev)
                    metrics = evaluate(labels, dev.tolist(), threshold, [0] * len(labels))
                    record = {'members': [candidates[i]['checkpoint'] for i in indices],
                              'member_models': [candidates[i]['model'] for i in indices],
                              'weights': weights, 'threshold': threshold, 'validation': metrics,
                              'threshold_trials': threshold_trials}
                    trials.append(record)
                    key = (*rank(metrics), -count)
                    if best is None or key > best[0]:
                        best = key, indices, weights, threshold, record
        _, indices, weights, threshold, selected = best
        # Even a single-member normalized wrapper preserves the newly tuned threshold.
        model = EnsembleBaseline([models[i] for i in indices], weights, category)
        model.threshold = threshold
        model.provenance = {'dataset': dataset, 'selection': 'development F2; accuracy then AUROC; fewer members on tie',
                            'split_sha256': source['split_sha256'], 'members': selected['members'],
                            'prior_final_test_exposure': True}
        model.save(folder / 'model.pt')
        validation, _ = score_samples(model, base, split['development'])
        # Check the production fusion exactly reproduces development search predictions.
        if abs(validation['f2'] - selected['validation']['f2']) > 1e-10:
            raise ValueError('Saved fusion does not reproduce development selection')
        final, predictions = score_samples(model, base, split['final_test'], save=folder / 'final')
        report = {'dataset': dataset, 'category': category, 'selected_model': 'ensemble',
                  'checkpoint': str((folder / 'model.pt').relative_to(ROOT)),
                  'selection_rule': model.provenance['selection'], 'validation': validation,
                  'selected': selected, 'trials': trials, 'final_metrics': final,
                  'prior_final_test_exposure': True,
                  'limitations': 'Reuses frozen final splits from the prior search; selection uses development only. Improvement on final scores is not guaranteed.'}
        (folder / 'predictions.json').write_text(json.dumps(predictions, indent=2, allow_nan=False) + '\n')
        (folder / 'results.json').write_text(json.dumps(report, indent=2, allow_nan=False) + '\n')
        print(dataset, category, 'development', validation['f2'], 'held-out', final['f2'], flush=True)
    finally:
        models.clear()
        release()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--device', default='mps')
    parser.add_argument('--category')
    args = parser.parse_args()
    reports = sorted((ROOT / 'outputs/training_f2').glob('*/*/results.json'))
    if args.category:
        reports = [p for p in reports if p.parent.name == args.category]
    with (ROOT / 'outputs/accelerator.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        for path in reports:
            run(path, args.device)
