# VisionQC architecture and saved-model adapters

The existing React web and Expo mobile clients send multipart images to FastAPI. The inspection router selects configured ML or VLM engines, validates the result, generates a heatmap, and persists the inspection with SQLAlchemy. Storage uses configured Supabase storage or local base64 image responses. The current local deployment uses SQLite and saved ML profiles. See [deployment and handoff](DEPLOYMENT.md) for configuration and verification limits.

```text
Web / Expo → existing inspection API → InspectionRouter
                                      ├─ saved ProfileMLEngine
                                      └─ configured VLM providers
                       → QualityGate → heatmap → storage + inspection history
```

The router supports `vlm_primary`, `vlm_only`, `model_primary`, `model_only` and `parallel_first_valid`. `DEMO_MODE=true` explicitly enables synthetic demonstration results. An unavailable real engine does not silently become a mock inspection.

## Saved profile contract

`backend/app/services/ml/base.py` defines `BaseMLEngine.inspect(image_bytes, product_id)`, `is_model_available(product_id)` and `load_model(product_id)`. `MLInspectionResult` contains a display anomaly score, optional confidence/map/defects, latency and an internal model identifier. Optional normalized ROI metadata is internal and rendered into the existing heatmap image.

`ProfileMLEngine` resolves a product UUID to a profile under `ML_MODEL_ROOT`, validates checkpoint containment, lazily loads a saved Autoencoder/PaDiM/PatchCore/ensemble and caches a bounded number of models. Inference never trains. Optional OpenCV or YOLO segmentation extracts an ROI; missing detection raises an error rather than returning PASS. Cropped maps are projected back onto the original image.

`experiments/export_profiles.py` creates immutable checkpoint versions and a catalog. The product profile attachment API accepts a catalog ID, not an arbitrary client checkpoint path. The web product screen can attach a matching profile. The original inspection response contract remains compatible; profile administration and experiment summaries are additional endpoints.

Model-only uploads preserve decoded pixels using lossless PNG without the VLM downscale/JPEG conversion. Each checkpoint then applies its own saved preprocessing. Camera images follow the same model adapter, but hardware and capture conditions need device-level verification.

## Scores and decisions

Training artifacts retain raw model scores. Deployment maps raw score `s` and calibrated threshold `t` to `s/(s+t)`, so the tuned cutoff is display score 0.5. Scores and heatmap intensities are not calibrated probabilities.

With `REVIEW_MARGIN=0`, scores strictly above the product threshold FAIL; equality or lower scores PASS. With a positive margin, values in the configured threshold band REVIEW. ML quality checks reject non-finite or out-of-range scores. VLM outputs also undergo decision, confidence and defect-list validation, including the configured minimum confidence. ML confidence is unavailable unless the model supplies a calibrated value; the numeric API placeholder remains 0 for compatibility and the clients display Unavailable.

Native anomaly maps are resized to the original image geometry, colored with OpenCV JET and encoded as PNG. ROI boxes can be drawn on this image without adding model-specific frontend fields. The viewer provides original, heatmap and overlay modes with adjustable opacity.

## Experiments

Normal-only fitting, held-out normal calibration, development F2 selection and frozen final evaluation are separate. `outputs/30shot_f2/` contains the fair shared-30-image baseline comparison. `outputs/final_core/` contains the exported core models' real metrics. Background expanded RGB/depth/D2S experiments have separate status files and are not represented as complete until their final reports exist. See [training protocol](TRAINING_F2.md) for cleaning, evaluation exposure and reporting limitations.
