# Recorded VisionQC results

Status: **partial; D2S stopped for submission; final evaluation unavailable**.

Selected using development F2. The rows below are actual frozen local final evaluations. Defects are positive.

| Dataset | Category | F2 | Accuracy | Precision | Recall | F1 | FAR | FRR |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| mvtec_ad | bottle | 96.77% | 96.97% | 100.00% | 96.00% | 97.96% | 4.00% | 0.00% |
| mvtec_ad | cable | 90.16% | 90.00% | 94.29% | 89.19% | 91.67% | 10.81% | 8.70% |
| mvtec_ad | capsule | 99.09% | 96.19% | 95.60% | 100.00% | 97.75% | 0.00% | 22.22% |
| mvtec_ad | metal_nut | 99.73% | 98.91% | 98.67% | 100.00% | 99.33% | 0.00% | 5.56% |
| mvtec_ad | screw | 90.62% | 89.06% | 95.51% | 89.47% | 92.39% | 10.53% | 12.12% |
| mvtec_ad | transistor | 91.77% | 95.00% | 96.67% | 90.62% | 93.55% | 9.38% | 2.08% |
| mvtec_ad2 | sheet_metal | 93.33% | 79.12% | 80.46% | 97.22% | 88.05% | 2.78% | 89.47% |
| mvtec_ad2 | vial | 83.73% | 76.79% | 85.37% | 83.33% | 84.34% | 16.67% | 42.86% |
| mvtec_ad2 | wallplugs | 85.61% | 59.17% | 60.00% | 95.83% | 73.80% | 4.17% | 95.83% |
| mvtec_loco | screw_bag | 84.39% | 63.74% | 65.70% | 90.86% | 76.26% | 9.14% | 84.69% |
| mvtec_3d_ad | cable_gland | 93.84% | 85.06% | 87.01% | 95.71% | 91.16% | 4.29% | 58.82% |
| mvtec_3d_ad | dowel | 95.64% | 94.23% | 97.53% | 95.18% | 96.34% | 4.82% | 9.52% |
| mvtec_3d_ad | tire | 87.50% | 73.33% | 78.75% | 90.00% | 84.00% | 10.00% | 85.00% |
| mvtec_ad2 | can | 74.26% | 47.69% | 51.72% | 83.33% | 63.83% | 16.67% | 96.55% |
| mvtec_loco | breakfast_box | 89.43% | 64.55% | 64.02% | 99.28% | 77.84% | 0.72% | 93.90% |
| mvtec_loco | splicing_connectors | 87.78% | 65.86% | 65.20% | 96.10% | 77.69% | 3.90% | 83.16% |

FAR = missed defects / defects; FRR = rejected normal images / normals. Profiles with high FRR are experimental and unsuitable for reliable automatic acceptance without further work.

Full metrics, confusion matrices, recorded parameters, nine 30-shot comparisons, depth results and ROI ablations are in [metrics.json](metrics.json). Benchmark latency differs from CPU API request latency.

## D2S segmentation

Training was stopped for the submission deadline. Saved intermediate checkpoints are retained locally; no final segmentation metrics are available.

## Evaluation limits

- Frozen final splits have been evaluated in earlier runs; these are repeated local evaluations.
- Category-specific benchmark profiles require matching product and image conditions.
- High F2 can coexist with unacceptable normal-image rejection; inspect FAR and FRR.
- D2S grocery segmentation is a domain ablation for industrial parts.
- Physical cameras and phone networking have not been tested.

See [the training runbook](../TRAINING_F2.md) and [deployment guide](../DEPLOYMENT.md) for reproducibility and integration checks. Datasets, weights and bulk example images stay outside Git.
