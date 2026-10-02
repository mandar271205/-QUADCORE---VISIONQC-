# Member 2 baselines and optional ROI

The Autoencoder is a reconstruction baseline. PaDiM is the pretrained-feature
baseline. PatchCore remains Member 1's primary detector. This implementation
extends the existing FastAPI ML adapter; web/mobile contracts stay unchanged.

## Current verification and remaining inputs

The code has been tested with Python 3.12 on macOS CPU, Anomalib 2.3.0,
PyTorch 2.14.1 and torchvision 0.29.1. Fixture smoke tests verify training,
held-out calibration, checkpoint reload and image output. A separate PaDiM
smoke test used the actual pretrained ResNet18 backbone. Fixture results are
not MVTec performance measurements.

Real Screw, Cable and Transistor experiments have **not been run**: the
repository contains no MVTec images, no Member 1 subset manifest, and no
PatchCore implementation/checkpoint. No real checkpoints, comparison metrics
or ROI improvement claims are supplied. The CLI stops on missing data and
records unavailable model metrics as null/blank with reasons in JSON.

## Existing architecture reused

- `app/services/ml/base.py`: existing BaseMLEngine and MLInspectionResult.
- `app/services/ml/registry.py`: lazy saved-profile adapter; demo still uses MockMLEngine.
- `app/core/config.py`: ML_MODEL_ROOT, ML_DEVICE, existing enable/mode switches.
- `app/services/heatmap/generator.py`: reused for experiment and API heatmaps.
- `app/services/inspection_router.py`: unknown ML confidence now uses 0.0
  instead of an invented 0.85; existing PNG serialization is preserved.
- No public routes, public schemas, web or mobile sources were changed.

The repository's `models/` ignore rule accidentally excluded its ORM package.
The missing `app/db/models` package has been restored to match the checked-in
Supabase SQL schema, and explicitly unignored. SQLAlchemy's async greenlet
runtime dependency is declared. API tests use isolated temporary SQLite DBs.

## Install and test

Use Python 3.11/3.12 (3.12 was tested); Python 3.14 cannot use the existing
backend's pinned NumPy 1.26.4 wheels.

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r backend/requirements-ml.txt
PYTHONPATH=backend python -m pytest backend/tests -q
PYTHONPATH=backend python -m app.services.ml.cli --help
```

The normal backend needs only `backend/requirements.txt`; torch, Anomalib and
scikit-learn are optional for experiments. Profile adapter imports are lazy.
YOLO is optional and not installed by the core ML requirements.

## Real data and shared subsets

Download real [MVTec AD](https://www.mvtec.com/research-teaching/datasets/mvtec-ad)
Screw, Cable and Transistor and extract without altering the splits:

```text
data/mvtec_ad/<category>/train/good/*.png
data/mvtec_ad/<category>/test/good/*.png
data/mvtec_ad/<category>/test/<defect>/*.png
data/mvtec_ad/<category>/ground_truth/<defect>/*_mask.png
```

Use **Member 1's exact selection**. Do not run subset creation if Member 1
already selected different files. The shared manifest format is:

```json
{
  "dataset": "mvtec_ad",
  "category": "screw",
  "seed": 42,
  "shots": 30,
  "train": ["train/good/<exact selected filename>.png"],
  "calibration": ["train/good/<held-out filename>.png"],
  "sha256": {"train/good/<filename>.png": "<actual file SHA256>"}
}
```

The example illustrates the format; an actual train list must contain exactly
30 unique files (20 is supported explicitly). Calibration must be nonempty,
disjoint and GOOD-only. Populate hashes for **every** listed file. Coordinate
held-out calibration files with Member 1 too. If Member 1 supplies a plain
filename list, convert that exact list to this format; do not resample it.

If the team has not selected images yet, explicitly generate the shared
selection once and have all three models reuse it:

```bash
PYTHONPATH=backend python -m app.services.ml.cli subset \
  --category screw --shots 30 --seed 42 --calibration-count 20 \
  --manifest experiments/subsets/screw_30.json
```

This is an explicit operation, never an automatic fallback during training.
It will not overwrite an existing manifest. Manifests are small and may be
committed; data and generated outputs are ignored. Training rejects paths
outside train/good, including any test/good paths. The manifest loader checks
category, shot count, uniqueness, path containment, split overlap and hashes.

## Train and reload

```bash
PYTHONPATH=backend python -m app.services.ml.cli train \
  --model autoencoder --manifest experiments/subsets/screw_30.json \
  --image-size 256 --epochs 50 --batch-size 8 --learning-rate 0.001 \
  --seed 42 --percentile 99 --device cpu

PYTHONPATH=backend python -m app.services.ml.cli train \
  --model padim --manifest experiments/subsets/screw_30.json \
  --image-size 256 --batch-size 8 --seed 42 --percentile 99 --device cpu

PYTHONPATH=backend python -m app.services.ml.cli predict \
  --model autoencoder --checkpoint outputs/checkpoints/autoencoder/screw.pt \
  --image data/mvtec_ad/screw/test/good/000.png \
  --heatmap outputs/heatmaps/autoencoder/screw/example.png
```

Repeat with cable/transistor manifests. Input filenames above must exist in
your extracted data. `--data-root`, `--output`, and `--device` are configurable;
CPU is the portable default. Use the **same** device for all compared models.

The Autoencoder uses RGB bilinear resize, no crop, [0,1] tensors, three encoder
and three decoder stages, Adam and squared reconstruction error. Its image
score is mean pixel error. PaDiM uses the same resize/color/geometry, followed
by ImageNet mean/std normalization required by the pretrained ResNet18. Its
layers are layer1/2/3, with 100 retained features; the image score is maximum
of Anomalib's smoothed Mahalanobis map. This model-specific normalization is
recorded in the checkpoint. Test and defect images never enter fitting or
threshold calibration. No default random augmentation is applied.

PaDiM uses the installed Anomalib 2.3.0 `Padim(...).model` API: training forward
passes populate its memory bank, then `fit()` estimates Gaussian statistics.
It does not use an automatic datamodule split, validation set, or postprocessor
that could silently tune thresholds on defects. See the official
[PaDiM documentation](https://anomalib.readthedocs.io/en/v2.1.0/markdown/guides/reference/models/image/padim.html)
and the installed 2.3.0 source when upgrading. The adapter rejects untested
Anomalib versions until their lifecycle has been checked.

The first pretrained PaDiM construction may download ResNet18 weights. Reload
constructs without downloading and restores the complete saved backbone,
feature-selection indices, Gaussian mean/covariance, config and threshold.
Inference never fits. CPU reload predictions are tested within a small floating
point tolerance, not bitwise equality. Only load trusted checkpoints; loading
uses torch's weights-only mode.

Threshold defaults to P99 of the held-out GOOD scores, configurable with
`--percentile` or an explicit positive `--threshold`. No defects tune it. Raw
scores are **not probabilities**. FAIL means raw score > threshold; equality
is PASS. A checkpoint cannot be saved before calibration.

## Fair comparison and Member 1 handoff

```bash
PYTHONPATH=backend python -m app.services.ml.cli compare \
  --manifest experiments/subsets/screw_30.json --image-size 256 --device cpu
```

The default is exactly 30-shot; `--allow-20-shot` explicitly enables the 20-shot
experiment. The command loads existing baseline checkpoints and never trains.
If one is missing, its row is marked unavailable. PatchCore is unavailable
until Member 1 provides both options:

```bash
PYTHONPATH=backend python -m app.services.ml.cli compare \
  --manifest experiments/subsets/screw_30.json \
  --patchcore-adapter app.services.ml.member1_adapter:PatchCoreBaseline \
  --patchcore-checkpoint outputs/checkpoints/patchcore/screw.pt
```

`member1_adapter` is a future module supplied by Member 1, not an existing
implementation. The class should implement the shared `Baseline` lifecycle:
fit, infer, predict, save and load, with name="patchcore", category, config,
threshold and provenance. `infer(rgb)` returns raw score, a finite anomaly map
at the configured shared image size, and optionally a reconstruction.
`load(path, device=...)` returns the fitted/calibrated instance. Set checkpoint
provenance using `comparison.provenance(document, config)` **only after actually
using those exact files and preprocessing**. Never relabel an incompatible
profile. Comparison checks category, manifest hash, image size, device and
preprocessing provenance. Comparison calls only load/predict, never fit.

If Member 1's checkpoint uses resize+center crop rather than shared full-frame
resize, reconcile preprocessing and mask geometry explicitly before comparing;
the present runner requires its shared full-frame geometry.

All models see the entire same sorted test set, identical mask resizing and
metric code. One unmeasured warmup precedes per-image timing. Timing includes
image decode/resize and model inference, synchronized by CPU transfers; it
excludes artifact writes and checkpoint loading. Hardware/device and latency
scope are logged. Cross-machine runs should not be compared as latency peers.

Metric definitions: positive class is DEFECT. FAR = defective units passed /
all defective units; FRR = GOOD units failed / all GOOD units. Precision,
recall and F1 use the calibrated threshold. Image and pixel AUROC use raw
scores/maps. Missing masks make pixel AUROC unavailable rather than treating
missing defects as normal. Single-class AUROC and absent-class rates are null
with explicit reasons. Undefined precision/recall use zero division = 0.

```text
outputs/checkpoints/{autoencoder,padim}/<category>.pt
outputs/heatmaps/<model>/<category>/calibration{,_overlay,_reconstruction}.png
outputs/metrics/<category>/{autoencoder,padim,patchcore,comparison}.csv
outputs/metrics/comparison.csv
outputs/comparison/<category>/{results,summary}.json
outputs/comparison/<category>/predictions.csv
outputs/comparison/{results,summary}.json
outputs/comparison/examples/<category>/<model>/<test type>/*.png
```

Example filenames are selected once with a fixed seed, independently of model
scores: 5 GOOD and 5 DEFECT (or all available if fewer). Each model uses those
same examples. Heatmap output includes raw map .npy, PNG and overlay; the
Autoencoder additionally saves reconstruction PNG. These are resized RGB
comparison examples, with threshold-relative map display, not per-image
min/max normalization. Score thresholds do not imply calibrated pixel
probabilities. Per-model/category metric CSVs and aggregate JSON preserve
unavailable rows; no fake PatchCore scores are generated.

## Backend profile registration and upload/camera frames

Place a trusted checkpoint and `<product UUID>.json` in ML_MODEL_ROOT:

```json
{"model": "autoencoder", "checkpoint": "autoencoder/screw.pt"}
```

Allowed names: autoencoder, padim, patchcore. PatchCore definitions also require
`"adapter": "app.services.ml.member1_adapter:PatchCoreBaseline"`. Relative
checkpoint paths must remain inside ML_MODEL_ROOT. Select the product via the
existing inspection endpoint; no model-specific frontend logic is needed.

```dotenv
ML_ENABLED=true
DEMO_MODE=false
INSPECTION_MODE=model_primary
ML_MODEL_ROOT=./models
ML_DEVICE=cpu
```

The public API's existing score contract is [0,1]. The adapter uses the monotonic
display scale `raw / (raw + calibrated_threshold)`: the calibrated cutoff maps
to **0.5**. Set product threshold to 0.5 to use that cutoff; a supervisor may
adjust it through the existing threshold endpoint. The existing REVIEW_MARGIN
still creates REVIEW near the cutoff. CLI benchmark verdicts remain binary.
Neither the display scale nor the confidence field is a calibrated probability.
For baselines, public confidence=0.0 denotes unavailable confidence, preserving
the existing numeric schema; no 0.85 confidence is invented. Raw score and
threshold remain available in experiment output.

Profiles load lazily in a worker thread and cache until definition/checkpoint
mtime changes. Model inference is serialized per adapter to avoid state races.
Missing profiles retain existing fallback behavior. DEMO_MODE still selects
MockMLEngine. Uploaded frames already use the inspection API; a camera client
can submit captured frames there without a new route.

## Optional D2S / ROI

[D2S](https://www.mvtec.com/research-teaching/datasets/mvtec-d2s) is exclusively
for training an independent product segmentation model. It is never used by
Autoencoder or PaDiM fitting. No D2S model has been trained in this workspace.

`ROIExtractor` has two implementations:

- OpenCV: largest foreground contour against estimated border background;
  a demo fallback suited to a plain background, not a learned D2S detector.
- YOLO: lazily imported Ultralytics segmentation with externally trained
  weights; selects the largest detected instance by mask area. Install
  Ultralytics in an optional environment and provide your D2S segmentation
  weights. Generic weights must not be described as D2S-trained.

An optional PatchCore ROI ablation is ready once Member 1 supplies its adapter:

```bash
PYTHONPATH=backend python -m app.services.ml.cli roi-compare \
  --category screw \
  --patchcore-adapter app.services.ml.member1_adapter:PatchCoreBaseline \
  --checkpoint outputs/checkpoints/patchcore/screw.pt \
  --extractor opencv
```

Use `--extractor yolo --roi-weights <segmentation checkpoint>` for YOLO.
`--roi-checkpoint` can provide a separately trained/calibrated ROI profile;
otherwise the report labels the run **inference_only_ablation**. Cropping a
full-frame-trained profile changes its input distribution: this alone is not
proof of deployment improvement. ROI-trained/calibrated profiles must use the
same extractor and crop policy at training and inference.

The run saves full-frame/ROI scores, thresholds, predictions, ground truth,
latency, boxes, masks drawn on frames, crops and paired heatmaps. ROI timing
includes detection/cropping; full-frame timing does not. Missing detection is
explicitly unavailable, not PASS; aggregate ROI metrics require detections
for every evaluated image. Do not claim reduced false positives until real
results demonstrate it.

For the existing backend add `"roi": "opencv"`, or `"roi": "yolo"` and
`"roi_weights": "roi/d2s-seg.pt"` to a product profile. Use this only with a
profile trained/calibrated for cropped inputs. Maps are projected back into
the original ROI box so frontend heatmaps stay aligned. No ROI detection
raises an inference error and leaves existing fallback/error handling intact.
The current public contract does not expose a separate segmentation overlay;
box overlays are saved by the experiment command.

## Implementation phase record (2 October 2026)

The table below records the initial implementation phase before the expanded
real-data request. For the subsequent downloads, PatchCore/depth/segmentation
training, F2 selection and separate 30-shot comparison, see
[the F2 training runbook](TRAINING_F2.md). Current real results and job status are
generated under `outputs/`; the initial missing-data entries below are historical.

| Phase | Files/work | Validation and remaining issues |
|---|---|---|
| 1: inspect | Full tracked tree, ML adapters, router, schemas, SQL schema, settings, requirements, tests | Empty workspace cloned from the requested repo. Missing ORM package and greenlet explained before integration. No PatchCore/data/subsets present. |
| 2: shared | shared/{config,data,preprocessing,result,metrics,baseline,visualization}.py | `pytest backend/tests/test_member2_shared.py`: 5 passed. Known confusion matrix, AUROC, manifest reproducibility, hashes, leakage and threshold tests. |
| 3: Autoencoder | autoencoder/{model,trainer,inference}.py | Normal-only fit, explicit calibration, checkpoint lifecycle and raw reconstruction error implemented. |
| 4: AE smoke | test_autoencoder.py | Temporary normal fixtures: 1 epoch, 32px, saved/reloaded checkpoint, written maps/reconstruction. Test passed; not a real benchmark. |
| 5: PaDiM | padim.py, requirements-ml.txt | Checked installed 2.3.0 signature, forward memory bank, fit and Gaussian dynamic buffers before implementing. |
| 6: PaDiM smoke | test_padim.py; separate pretrained smoke command | Fit/calibrate/save/reload/heatmap passed. Initial bitwise check failed by ~0.00004; saved buffers were identical and numerical tolerance check passed. Unit test stays offline; separate smoke uses real pretrained weights. |
| 7: comparison | comparison.py, factory.py, cli.py, test_comparison.py | Fixture test verifies same examples, outputs, null missing-model rows and rejection of provenance mismatches. No training occurs during comparison. |
| 8: Screw | `cli compare --manifest experiments/subsets/screw_30.json` | Exit 2: missing shared manifest/data. Real experiment not run. |
| 9: Cable/Transistor | Same compare command for their category manifests | Exit 2 for both: same missing inputs. Real experiments not run. |
| 10: optional ROI | roi.py, roi_experiment.py, profile_engine.py, registry/config, ROI tests | OpenCV geometry, projected backend maps, paired export and unavailable detections tested. D2S/YOLO training and real PatchCore ablation remain unrun. |
| 11: integration/docs | Restored ORM, isolated DB tests, README, this runbook, .env.example | `PYTHONPATH=backend .venv/bin/python -m pytest backend/tests -q`: **22 passed**. API upload with trained fixture profile, MockMLEngine and existing CRUD/analytics tests pass. |

Additional executed checks: `python -m pip check` reported no broken
requirements; `git diff --check` passed; compileall passed for new ML/ORM
modules. A process deliberately blocking torch/anomalib/sklearn/ultralytics
imports successfully imported FastAPI and ran MockMLEngine. Existing
Pydantic/FastAPI/datetime and Anomalib deprecation warnings remain.

At the end of this initial phase, remaining deliverables required the real dataset, the team's exact shared
normal subset/calibration manifest, and Member 1's compatible PatchCore
adapter/checkpoint. D2S segmentation weights are optional. Dataset/model
artifacts and fixture outputs have not been committed or presented as
trained benchmark deliverables.
