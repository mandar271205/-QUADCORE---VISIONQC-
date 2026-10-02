# Submission handoff

This submission contains the implemented Member 2 backend, web and mobile integration and the completed anomaly/depth experiments. At the user request, the long D2S segmentation run was stopped to meet the submission deadline. Section 7.5 final D2S evaluation and the D2S industrial ROI ablation remain incomplete; saved intermediate checkpoints are not a validated final segmentation model.

## Recorded core performance

Six category-specific MVTec AD profiles, pooled over 591 frozen final images:

| Metric | Value |
|---|---:|
| Accuracy | 93.74% |
| F2 | 94.83% |
| F1 | 95.46% |
| Precision | 96.53% |
| Recall | 94.42% |

Confusion matrix (normal, defect): `[[165, 14], [23, 389]]`. These combine six category profiles; they do not describe a universal classifier. Profiles and thresholds were selected by development F2. Final splits were evaluated previously; these are repeated local results. Some extended profiles have high false rejects. Full 16-category metrics, selected parameters, nine 30-shot comparisons, depth and ROI results are in [recorded results](results/README.md) and [metrics.json](results/metrics.json).

## Running the trained submission

The prepared local workspace is `/Users/vats/Desktop/VisionQC`. The web app is `http://127.0.0.1:5174`; API docs are `http://127.0.0.1:8001/docs`. Choose a benchmark product matching the uploaded image category, then inspect. The app returns the saved-model decision, score, heatmap and inspection history.

Trained weights are preserved in the local `models/` directory (approximately 2.1 GB). Datasets, model weights, database and secrets are excluded from Git. A fresh Git clone needs the exported `models/` directory and generated comparison outputs, or a reproduced training/export run, before real model inference works. GitHub code alone does not contain the trained weights. Copy the model directory and `outputs/30shot_f2` to the recipient workspace separately; configure their own environment and run `experiments/export_profiles.py --seed-products` only when the corresponding training outputs are also available. No API credentials are included. See [deployment](DEPLOYMENT.md) for configuration and scope.

## Verification

45 backend tests passed; web production build and mobile TypeScript passed. All 32 saved-profile/API parity uploads across the 16 categories pass with heatmaps and persisted history. These upload checks verify integration, not classification accuracy. The earlier iOS export also passed. Physical cameras and phone networking have not been tested. The web build has a bundle-size warning.
