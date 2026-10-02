"""Optional full-frame versus ROI inference ablation, with honest provenance.

Without a separately ROI-trained profile this measures an input distribution
change, not a validated ROI deployment improvement. Missing detections are
recorded as unavailable rather than assigning PASS.
"""
import io
import json
import time
from pathlib import Path
from PIL import Image
import numpy as np
from app.services.ml.comparison import write_csv
from app.services.ml.roi import overlay
from app.services.ml.shared.data import test_samples
from app.services.ml.shared.metrics import evaluate


def run_roi_experiment(root: Path, category: str, model, extractor, output: Path,
                       roi_model=None, samples=None) -> dict:
    if model.name != 'patchcore' or model.category != category:
        raise ValueError('ROI experiment requires Member 1 category-specific PatchCore')
    cropped_model = roi_model or model
    if cropped_model.name != 'patchcore' or cropped_model.category != category:
        raise ValueError('ROI profile must be a category-specific PatchCore')
    fixed_samples = samples is not None
    samples = samples if fixed_samples else test_samples(root,category)
    if not samples:
        raise ValueError('ROI experiment requires evaluation samples')
    output.mkdir(parents=True,exist_ok=True)
    rows = []
    # Identical warmup policy; exclude it from latency.
    model.predict(samples[0][0])
    cropped_model.predict(samples[0][0])
    for path,label,_ in samples:
        relative = path.relative_to(root/category).as_posix()
        prefix = output/'examples'/path.parent.name/path.stem
        full, _ = model.predict(path,prefix.with_name(prefix.name+'_full_heatmap.png'))
        start = time.perf_counter()
        with Image.open(path) as image:
            original = np.asarray(image.convert('RGB'))
        roi = extractor.extract(original)
        row = {'filename': relative,'ground_truth': label,'full_frame_score':full.anomaly_score,
               'full_frame_threshold':full.threshold,'full_frame_prediction':full.verdict,
               'full_frame_latency_ms':full.latency_ms,'roi_score':None,'roi_threshold':None,
               'roi_prediction':None,'roi_latency_ms':None,'bbox':None,'status':'no_roi'}
        if roi:
            cropped = roi.crop(original)
            buffer = io.BytesIO(); Image.fromarray(cropped).save(buffer,format='PNG')
            # Timing excludes heatmap output writes for both paths.
            prediction, _ = cropped_model.predict(buffer.getvalue())
            elapsed = (time.perf_counter()-start)*1000
            cropped_model.predict(buffer.getvalue(),prefix.with_name(prefix.name+'_roi_heatmap.png'))
            Image.fromarray(overlay(original,roi)).save(prefix.with_name(prefix.name+'_bbox.png'))
            Image.fromarray(cropped).save(prefix.with_name(prefix.name+'_crop.png'))
            row.update(roi_score=prediction.anomaly_score,roi_threshold=prediction.threshold,
                       roi_prediction=prediction.verdict,roi_latency_ms=elapsed,bbox=list(roi.bbox),status='evaluated')
        rows.append(row)
    full_metrics = evaluate([r['ground_truth'] for r in rows],[r['full_frame_score'] for r in rows],
                            model.threshold,[r['full_frame_latency_ms'] for r in rows])
    roi_metrics = None
    if all(r['status']=='evaluated' for r in rows):
        roi_metrics = evaluate([r['ground_truth'] for r in rows],[r['roi_score'] for r in rows],
                               cropped_model.threshold,[r['roi_latency_ms'] for r in rows])
    report = {'category':category,'mode':'separate_roi_profile' if roi_model else 'inference_only_ablation',
              'evaluation_scope':'frozen final holdout' if fixed_samples else 'official test set; may include development samples',
              'extractor':type(extractor).__name__,'full_profile':model.provenance,
              'roi_profile':cropped_model.provenance,'full_frame_metrics':full_metrics,'roi_metrics':roi_metrics,
              'roi_metrics_unavailable':None if roi_metrics else 'ROI detection missing for one or more images',
              'note':'No improvement claim is made. Separate ROI training/calibration is needed for deployment.',
              'predictions':rows}
    write_csv(output/'comparison.csv',rows,list(rows[0]))
    (output/'results.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    return report
