"""
Member 3 benchmark results integration.

This module surfaces Member 3's pre-computed benchmark metrics for
the /experiments/comparison endpoint.

IMPORTANT: Member 3 checkpoints are NOT used for production inspection
routing. This module is READ-ONLY benchmark data integration only.
"""
from __future__ import annotations

# ──────────────────────────────────────────────────────────────
# Member 3 summary — sourced from:
#   member3-audit/VisionQC_Member3_Integration_Handoff/
#     config/member3_inference_config.json
#     final_summary/member3_backend_summary.json
#     README_INTEGRATION.md
# ──────────────────────────────────────────────────────────────
MEMBER3_METRICS: list[dict] = [
    {
        "member": 3,
        "dataset": "MVTec AD2",
        "category": "sheet_metal",
        "model": "PatchCore",
        "backbone": "wide_resnet50_2",
        "image_auroc": 0.7174,
        "pixel_auroc": 0.7878,
        "latency_ms": 351.47,
        "threshold_P95": 0.384615,
        "threshold_P99": 0.476923,
        "notes": "AD2 changed-lighting evaluation; AUROC measured on public test set.",
    },
    {
        "member": 3,
        "dataset": "MVTec AD2",
        "category": "vial",
        "model": "PatchCore",
        "backbone": "wide_resnet50_2",
        "image_auroc": 0.7667,
        "pixel_auroc": None,
        "operational_f1": 0.7368,
        "latency_ms": 277.59,
        "threshold_P95": 0.1091,
        "threshold_P99": 0.4119,
        "notes": "Best single model on vial; P95 threshold from normal validation scores.",
    },
    {
        "member": 3,
        "dataset": "MVTec AD2",
        "category": "vial",
        "model": "EfficientAD-small (10-epoch exp.)",
        "backbone": "EfficientAD",
        "image_auroc": 0.7461,
        "pixel_auroc": 0.5942,
        "latency_ms": 281.04,
        "peak_gpu_gb": 0.474,
        "notes": (
            "10-epoch Colab experiment. Reduced GPU memory vs PatchCore "
            "but no measured latency advantage."
        ),
    },
    {
        "member": 3,
        "dataset": "MVTec LOCO",
        "category": "screw_bag",
        "model": "PatchCore",
        "backbone": "wide_resnet50_2",
        "image_auroc": None,
        "logical_auroc": 0.5772,
        "structural_auroc": 0.8408,
        "threshold_P95": 0.229092,
        "threshold_P99": 0.448642,
        "notes": (
            "Structural anomalies detected more reliably than logical anomalies. "
            "LOCO evaluation protocol."
        ),
    },
    {
        "member": 3,
        "dataset": "MVTec LOCO",
        "category": "splicing_connectors",
        "model": "PatchCore",
        "backbone": "wide_resnet50_2",
        "image_auroc": None,
        "logical_auroc": 0.7818,
        "structural_auroc": 0.8593,
        "threshold_P95": 0.165868,
        "threshold_P99": 0.352752,
        "notes": "Better logical AUROC than screw_bag on LOCO protocol.",
    },
    {
        "member": 3,
        "dataset": "MVTec 3D",
        "category": "cable_gland",
        "model": "RGB PatchCore",
        "backbone": "wide_resnet50_2",
        "image_auroc": 0.9206,
        "pixel_auroc": 0.9893,
        "notes": "RGB-only baseline for 3-D evaluation.",
    },
    {
        "member": 3,
        "dataset": "MVTec 3D",
        "category": "cable_gland",
        "model": "Depth prototype (nearest-neighbour geometry memory)",
        "backbone": "custom",
        "image_auroc": 0.9940,
        "threshold_P95": 0.049316,
        "threshold_P99": 0.052839,
        "notes": (
            "Depth-only prototype using Z-channel of XYZ TIFF. "
            "Training on 30 normal samples; 30 000 memory vectors. "
            "Depth-only exceeded equal-weight RGB+Depth fusion on this run."
        ),
    },
    {
        "member": 3,
        "dataset": "MVTec 3D",
        "category": "cable_gland",
        "model": "RGB + Depth fusion (equal weight)",
        "backbone": "wide_resnet50_2 + custom depth",
        "image_auroc": 0.9923,
        "notes": "50/50 weighted fusion of RGB PatchCore and depth prototype scores.",
    },
]

# Framework info
MEMBER3_FRAMEWORK = {
    "anomalib": "2.6.2",
    "torch": "2.11.0+cu130",
    "training_environment": "Google Colab / CUDA",
    "normal_images_used": "Standard MVTec AD2 / LOCO / 3D training splits",
    "thresholds_derivation": "P95 / P99 of normal validation scores",
}


def get_member3_benchmark_summary() -> dict:
    """Return a serialisable summary of Member 3's benchmark results."""
    return {
        "member": 3,
        "framework": MEMBER3_FRAMEWORK,
        "routing_status": "NOT_ROUTED",
        "routing_note": (
            "Member 3 checkpoints are not used for live inspection routing. "
            "Results are benchmark-only for comparison and judge presentation."
        ),
        "highlights": {
            "cable_gland_depth_auroc": 0.9940,
            "cable_gland_rgb_depth_fusion_auroc": 0.9923,
            "splicing_connectors_structural_auroc": 0.8593,
            "vial_patchcore_auroc": 0.7667,
        },
        "categories": MEMBER3_METRICS,
    }
