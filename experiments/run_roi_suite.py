"""Real full-frame/cropped ablations with explicit missing ROI and domain limits."""
import argparse
import fcntl
import json
import torch
from pathlib import Path
from app.services.ml.factory import model_class
from app.services.ml.roi import OpenCVROIExtractor, YOLOROIExtractor
from app.services.ml.roi_experiment import run_roi_experiment
from app.services.ml.comparison import write_csv
from train_suite import release

ROOT = Path(__file__).resolve().parents[1]


def write_summary(label):
    root = ROOT / 'outputs/roi' / label
    rows = []
    for category in ('screw', 'cable', 'transistor'):
        report = json.loads((root/category/'results.json').read_text())
        for variant, field in [('full_frame','full_frame_metrics'),('roi_crop','roi_metrics')]:
            metrics = report[field] or {}
            rows.append({'category':category,'variant':variant,'evaluation_scope':report['evaluation_scope'],
                         'samples':len(report['predictions']),
                         'missing_roi':sum(r['status']!='evaluated' for r in report['predictions']),
                         **{key:metrics.get(key) for key in ('f2','f1','precision','recall','accuracy',
                                  'false_accept_rate','false_reject_rate','latency_ms')}})
    write_csv(root/'summary.csv',rows,list(rows[0]))
    lines=['# ROI inference ablation','',
           'Family-selected standalone PatchCore, frozen final images, unchanged full-frame threshold. Cropped inputs are not separately trained or calibrated. These results do not validate ROI deployment.',
           '', '| Category | Input | Images | F2 | Accuracy | FAR | FRR |',
           '|---|---|---:|---:|---:|---:|---:|']
    for row in rows:
        values=[row['category'],row['variant'],str(row['samples'])]+[
            'Unavailable' if row[k] is None else f'{100*row[k]:.2f}%' for k in
            ('f2','accuracy','false_accept_rate','false_reject_rate')]
        lines.append('| '+' | '.join(values)+' |')
    lines+=['','Per-category `comparison.csv` and `results.json` retain paired scores, boxes, predictions and latency. `examples/` contains full maps, crop maps, crops and box/mask overlays.',
            '', 'D2S segmentation on industrial parts is a domain ablation; D2S grocery classes are not validated industrial part detectors.']
    (root/'SUMMARY.md').write_text('\n'.join(lines)+'\n')


def run(extractor, label, device):
    for category in ('screw', 'cable', 'transistor'):
        output = ROOT / 'outputs/roi' / label / category
        if (output / 'results.json').exists():
            prior = json.loads((output / 'results.json').read_text())
            if prior.get('evaluation_scope') != 'frozen final holdout':
                raise RuntimeError(f'Archive legacy evaluation before running: {output}')
            continue
        path = ROOT / 'outputs/training_f2/mvtec_ad' / category / 'results.json'
        report = json.loads(path.read_text())
        selected = next(row for row in report['final_results'] if row['model'] == 'patchcore')
        trial = next(t for t in report['trials'] if t['model'] == 'patchcore' and t['parameters'] == selected['parameters'])
        model = model_class('patchcore').load(ROOT / trial['checkpoint'], device)
        model.threshold = selected['threshold']
        model.provenance['threshold_selection'] = 'labelled_development_F2'
        split=json.loads((path.parent/'split.json').read_text())
        base=ROOT/'data/mvtec_ad'/category
        samples=[(base/item['filename'],item['label'],None) for item in split['final_test']]
        try:
            result = run_roi_experiment(ROOT / 'data/mvtec_ad', category, model, extractor, output,samples=samples)
            print(label, category, 'missing ROI:', sum(r['status'] != 'evaluated' for r in result['predictions']), flush=True)
        finally:
            del model
            release()
    write_summary(label)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--device', default='mps')
    parser.add_argument('--yolo-weights', type=Path)
    args = parser.parse_args()
    torch.set_num_threads(4)
    with (ROOT / 'outputs/accelerator.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if args.yolo_weights:
            # D2S objects differ from these industrial objects. This is an explicit
            # detection/domain ablation; no ROI improvement or deployment claim.
            run(YOLOROIExtractor(args.yolo_weights), 'd2s_domain_ablation', args.device)
        else:
            run(OpenCVROIExtractor(), 'opencv', args.device)
