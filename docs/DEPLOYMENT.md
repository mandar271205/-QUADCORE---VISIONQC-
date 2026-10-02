# Trained VisionQC deployment and Member 2 handoff

The existing FastAPI, web and Expo app share the original inspection response contract. The local configuration uses real saved model profiles, without API keys or synthetic demo fallback. Select a matching product, upload a PNG/JPEG/WebP image, and inspect: the response includes PASS/FAIL, anomaly score, heatmap and persisted inspection history. Model-only inference requires an attached trained profile. Unknown products or unavailable profiles return an actionable error.

## Local application

The modified app runs at **http://127.0.0.1:5174**, with API documentation at **http://127.0.0.1:8001/docs**. Another checkout uses ports 5173/8000; these ports avoid that collision.

For a fresh setup, copy `.env.model.example` to the root `.env` (preserve an existing configured file). Install backend dependencies and `backend/requirements-ml.txt`; the optional segmentation worker additionally uses `backend/requirements-roi.txt`. Generated model exports are required before model-only inference.

Run from this repository root. Keep generated `models/`, `outputs/` and the root `.env` together; checkpoints and datasets are intentionally ignored by Git.

```sh
PYTHONPATH=backend .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8001
```

In a separate terminal:

```sh
cd web
VITE_API_URL=http://127.0.0.1:8001/api/v1 npm run dev -- --host 127.0.0.1 --port 5174
```

The root `.env` selects `INSPECTION_MODE=model_only`, `ML_ENABLED=true`, `ML_DEVICE=cpu`, `MOBILE_USE_ML=true`, `DEMO_MODE=false`, `REVIEW_MARGIN=0` and a 30-second engine timeout. `web/.env` points to this API. A trained threshold maps to display score 0.5; the score is **not a defect probability**. A positive review margin enables REVIEW near the decision threshold. There is no calibrated model confidence; the client displays it as unavailable.

Benchmark products have their profiles attached. Other products can attach a server-exported profile in Products → product detail. Use a profile only for its matching category and acquisition conditions. These are category-specific anomaly models, not a universal object classifier. The comparison page shows the separate 30-shot baselines, not the final all-normal models.

For Expo, `mobile/.env` sets `EXPO_PUBLIC_API_PORT=8001`; the iOS default is localhost and the Android emulator uses 10.0.2.2. A physical phone needs `EXPO_PUBLIC_API_URL=http://<computer-LAN-address>:8001/api/v1` and an API listener reachable on the LAN. Physical camera capture and device networking have not been verified. Web camera permission, framing and actual factory lighting also need device-level acceptance testing.

## Final core model artifacts

`outputs/final_core/REPORT.md` reports F2, recall, precision, F1, accuracy and image/pixel AUROC for the six exported MVTec AD profiles. `outputs/final_core/models.json` records immutable checkpoint paths, saved parameters (including fusion member settings), and full metrics. `models/catalog.json` maps profile IDs to definitions; product UUID profile files bind those definitions to inspections.

The expanded search compares normal-only Autoencoder, PaDiM and PatchCore, then higher-resolution PatchCore and development-selected score fusion. Model fitting never uses defect images. Thresholds and fusion weights use development labels. Exact development ties retain the prior checkpoint and threshold. Final labels do not select candidates. The recorded final splits have been evaluated in earlier runs, so these are repeated local evaluations, not a newly unseen official benchmark. F2 is the selection priority; neither perfect accuracy nor a global optimum is established. Transistor's refined final F2 declined despite its better development F2.

`outputs/validation/upload_all_profiles_e2e.json` verifies 32 real uploads across all 16 profiles (the earlier core-only check is `upload_e2e.json`) against the exported checkpoints: matching scores/decisions, image and heatmap storage, history, and the nine comparison rows. `outputs/validation/mobile_api.json` additionally checks two mobile-client uploads and their persisted client type. These checks verify integration parity, not a new classification benchmark.

## Sections 7.1–7.11

| Section | Implementation and artifacts | Verification / current scope |
|---|---|---|
| 7.1 shared MVTec data | `shared/data.py`, `experiments/data_protocol.py`, `outputs/30shot_f2/*/manifest.json` | Fixed seed and the same 30 normal filenames for all three models; separate full-normal fit/calibration/dev/final manifests. |
| 7.2 Autoencoder | `backend/app/services/ml/autoencoder/` | Normal-only training; saved/reloaded checkpoints, reconstruction, raw maps and overlays. Three core category runs and three 30-shot runs completed. |
| 7.3 PaDiM | `backend/app/services/ml/padim.py` | Anomalib 2.3.0, resnet18 layers 1/2/3, saved statistics; same category protocols. |
| 7.4 fair PatchCore comparison | `patchcore.py`, `comparison.py`, `experiments/train_30shot.py` | All nine 30-shot combinations completed, common subset/preprocessing/evaluation lists. |
| 7.5 D2S segmentation | `experiments/train_d2s.py` | All 7,980 public train/validation images audited and converted; frozen 4,380/1,800/1,800 split. Development mask F2 selection and original-mask final metrics implemented; training/final report pending. |
| 7.6 ROI adapters | `backend/app/services/ml/roi.py` | YOLO segmentation largest instance and OpenCV fallback interfaces; no detection is unavailable, never a fabricated PASS. |
| 7.7 common model interface | `factory.py`, `profile_engine.py`, `catalog.py` | Category profiles and saved inference integrate with the existing router; checkpoints never retrain on upload. |
| 7.8 metrics and examples | `outputs/30shot_f2/{comparison.csv,results.json}`, `/comparison` | F2/F1/precision/recall, accuracy, AUROC, FAR/FRR, latency and common five GOOD/five DEFECT overlays for each category/model. |
| 7.9 ROI comparison | `roi_experiment.py`, `experiments/run_roi_suite.py`, `outputs/roi/` | Full-frame versus crop on frozen final images; paired boxes/crops/maps. Inference-only ablation using each family-selected standalone PatchCore, not the final fusion model; not separately trained ROI deployment. Earlier mixed-split outputs preserved in `outputs/roi_legacy_before_frozen_holdout/`. |
| 7.10 upload/camera adapter | Existing `/inspections`, web Live Inspection and Expo inspection screens | Lossless model upload preprocessing, model score, projected heatmap/optional ROI box and persisted history; 12 real API parity cases passed. Camera hardware remains untested. |
| 7.11 handoff | This guide, `docs/TRAINING_F2.md`, source/tests/checkpoints/maps/reports | Backend tests, web build, mobile type check and iOS export pass. Extended RGB and depth experiments are complete; D2S training and final metrics remain pending. |

Module names above without a prefix are under `backend/app/services/ml/`. The actual 30-shot manifest filename is retained in each category's output folder; consult its JSON provenance rather than resampling.

## Remaining background experiments

All 18 linked archives are downloaded and extracted. All 16 anomaly categories, the frozen OpenCV ROI ablations and three depth prototypes are complete. D2S segmentation training and its domain ROI ablation remain active or pending. Segmentation waits for the anomaly/depth suite to release MPS; its multi-trial run can take hours. The supervisor generates `outputs/FINAL_REPORT.md` and `outputs/FINAL_RESULTS.json` only after all required reports exist. The core export does not mean all extended experiments are finished.

Inspect `data/download_status.json`, `outputs/training_f2/status.json`, `outputs/primary_worker_status.json`, `outputs/experiment_status.json` and `outputs/d2s/status.json` for running, failed or complete states. Failures are explicit and include log paths. Check existing processes before resuming to avoid duplicate training. D2S grocery segmentation applied to industrial parts is a domain ablation, not validated industrial ROI training. The depth model is a normal-only Gaussian feature prototype.

The current backend suite has 45 passing tests. The production web build passes with a bundle-size warning. Mobile TypeScript and iOS bundling pass; this is not a claim of physical-device testing. `DEMO_MODE=true` remains available only as an explicit synthetic demonstration setting.
