# F2-focused real-data training

The accuracy-focused run uses every clean normal training image except a
held-out normal calibration set. A separate 30-image comparison covers Screw,
Cable and Transistor. F2 (beta = 2) is the primary selection metric: recall has
four times the weight of precision in its harmonic mean. Defect is the positive
class. Accuracy and F1 remain reported metrics.

## Data and cleaning

`experiments/datasets.json` contains the 18 archives linked in the supplied
training plan: six MVTec AD categories, four AD2 categories, three LOCO
categories, three 3D AD categories, and D2S images and annotations. These are
the document's linked categories, not every category offered by these datasets.
Downloads resume using verified byte ranges. Extraction rejects unsafe paths
and links, and records archive size and SHA-256. Originals stay in `data/`.

Every anomaly image is decoded and hashed by RGB pixels and dimensions.
Corrupt or duplicated normal training images and train/evaluation overlaps are
excluded with an audit record. Evaluation corruption blocks the category.
Identical evaluation images stay in the same partition; conflicting labels
block training. Masks are checked for matching geometry. Missing defect masks
make pixel metrics unavailable rather than assigning invented scores.

For each category, `split.json` freezes the clean normal fitting set, held-out
normal calibration set, labelled development set and final test set. Normal
calibration uses 10% of clean normals with a minimum of 20 images. The official
labelled evaluation data is grouped by duplicate hash and stratified by label:
20% development, 80% final. AD2 uses public labels only. On resume, frozen image
hashes are verified. Development and final scores are local split scores, not
official full-benchmark test results.

## Search and evaluation

MVTec AD compares Autoencoder, PaDiM and PatchCore. AD2, LOCO and 3D RGB use
PatchCore. The search varies image resolution, Autoencoder learning rate and
epochs, PaDiM feature count, and PatchCore backbone and coreset size. The exact
candidate grid and each result are recorded in `experiments/train_suite.py`
and category `trials/*/validation.json` files. All initial three candidates run;
the fourth PatchCore candidate runs unless two preceding trials fail to improve.

Threshold candidates include held-out normal percentiles and boundaries
between development scores. Maximum development F2 selects the threshold.
Development F2, then image AUROC, then pixel AUROC select the model. Final
labels never select the winner or threshold. Each family's selected checkpoint
is evaluated on the final split once. A finite search cannot establish a global
optimum. Small development sets can make the chosen threshold uncertain.

Earlier runs have already evaluated the frozen core final splits, including
refinement. These are repeated local evaluations, not fresh unseen official
benchmark tests. Development data alone selects parameters and thresholds.
The earlier checkpoints are reused where available, with threshold selection
repeated using development F2 only.

F2 can favor rejecting many normal products. The report therefore also includes
precision, recall, accuracy, balanced accuracy, F1, image/pixel AUROC, average
precision, confusion matrices, latency, false accept rate (missed defects / all
defects) and false reject rate (rejected normals / all normals). Display score
normalization is not a probability calibration.

The 30-shot comparison uses exactly the same sampled 30 normals for all three
models, identical 256-pixel preprocessing, and the full run's calibration,
development and final lists. Depth uses a normal-only diagonal Gaussian on
aligned Z and Sobel features; development F2 selects regularization and RGB/depth
fusion weight. This is a prototype, not a state-of-the-art point-cloud model.

D2S uses official training annotations and halves the public validation images
into development and final sets. YOLOv8 segmentation candidates vary model size,
learning rate and epoch budget, with validation mask F2 controlling checkpoints
and early stopping. Polygon conversion loss is audited. Final object-level
precision, recall, F1 and F2 use original COCO masks at mask IoU 0.5, and COCO
mask mAP is also reported. Private official test labels are unavailable.
Image-classification accuracy does not apply to this segmentation evaluation.

## Running and resuming

From the repository root, use the installed `.venv`. Run each command in its
own process. Check existing workers first to avoid duplicate jobs.

```sh
.venv/bin/python -u experiments/download_datasets.py
PYTHONPATH=backend PYTORCH_ENABLE_MPS_FALLBACK=1 .venv/bin/python -u experiments/train_suite.py
PYTHONPATH=backend PYTORCH_ENABLE_MPS_FALLBACK=1 .venv/bin/python -u experiments/train_d2s.py --wait --device mps --after-anomaly-suite
PYTHONPATH=backend PYTORCH_ENABLE_MPS_FALLBACK=1 .venv/bin/python -u experiments/finish_training.py
```

Training waits for extraction markers. A shared accelerator file lock prevents
the anomaly, depth, 30-shot and segmentation jobs from competing for MPS memory.
The supervisor starts the 30-shot and depth jobs after primary training and
generates the combined report after D2S completes. Failed jobs are explicit and
require their concrete error to be fixed before resuming; they are not retried
indefinitely. Completed checkpoints and reports are reused.

Live status files:

- `data/download_status.json`: archive progress, hashes and failures.
- `outputs/training_f2/status.json`: category, trial, parameters and metrics.
- `outputs/training_f2/final_metrics.csv`: completed real held-out evaluations.
- `outputs/experiment_status.json`: supervisor progress or error.

Final artifacts are `outputs/FINAL_REPORT.md` and `outputs/FINAL_RESULTS.json`.
Category reports retain parameter trials, audit records and predictions. The
30-shot, depth and D2S outputs are retained separately. Data, generated outputs
and trained checkpoints are ignored by Git.

## Verification

The current backend suite passes 45 tests, including known F2/confusion metrics,
threshold selection, mask F2 checkpoint fitness, frozen splits, checkpoint
round trips, ROI geometry and backend integration. `pip check`, compileall and
`git diff --check` pass. Test fixture metrics are never reported as real training
results. Training progress and actual benchmark results are read from the
generated output files, not hard-coded in this runbook.

## Core refinement and deployment

`experiments/refine_core.py` evaluates 384-pixel Wide ResNet and 512-pixel
ResNet PatchCore with a reproducible 60,000-patch training budget.
`experiments/improve_models.py` compares singles and weighted score fusion on
development F2, retaining prior checkpoints and thresholds on exact ties.
Final metrics are evaluated after selection. A better development score does
not guarantee a better final score; the Transistor result illustrates this.

`experiments/export_profiles.py --seed-products` exports immutable checkpoint
versions and attaches profiles to benchmark products. The core report lives in
`outputs/final_core/REPORT.md`, with full metrics in `models.json` beside it.
See [the deployment guide](DEPLOYMENT.md) for application setup, upload checks,
ROI scope, mobile verification and the full 7.1–7.11 handoff.
