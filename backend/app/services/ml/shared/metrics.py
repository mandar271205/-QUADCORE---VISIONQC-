"""Shared metric definitions. Positive class is DEFECT (FAIL)."""
import numpy as np
from sklearn.metrics import roc_auc_score, precision_recall_fscore_support, accuracy_score, balanced_accuracy_score, average_precision_score, confusion_matrix, fbeta_score


def evaluate(labels, scores, threshold: float, latencies, masks=None, maps=None) -> dict:
    labels, scores = np.asarray(labels), np.asarray(scores, dtype=float)
    latency = np.asarray(latencies, dtype=float)
    if not len(labels) or len(labels) != len(scores) or len(labels) != len(latency):
        raise ValueError("Nonempty matching labels, scores and latencies required")
    if not np.isin(labels, [0, 1]).all() or not np.isfinite(scores).all() or not np.isfinite(latency).all():
        raise ValueError("Invalid labels or nonfinite measurements")
    if not np.isfinite(threshold) or threshold <= 0 or (latency < 0).any():
        raise ValueError("Invalid threshold or latency")
    predictions = scores > threshold
    precision, recall, f1, _ = precision_recall_fscore_support(
        labels, predictions, average="binary", zero_division=0)
    defects, good = labels == 1, labels == 0
    result = {"image_auroc": float(roc_auc_score(labels, scores)) if len(np.unique(labels)) == 2 else None,
              "accuracy": float(accuracy_score(labels, predictions)),
              "balanced_accuracy": float(balanced_accuracy_score(labels, predictions)) if len(np.unique(labels)) == 2 else None,
              "average_precision": float(average_precision_score(labels, scores)) if defects.any() else None,
              "confusion_matrix": confusion_matrix(labels, predictions, labels=[0,1]).tolist(),
              "pixel_auroc": None, "f1": float(f1), "precision": float(precision), "recall": float(recall),
              "f2": float(fbeta_score(labels, predictions, beta=2, zero_division=0)),
              "false_accept_rate": float((~predictions[defects]).mean()) if defects.any() else None,
              "false_reject_rate": float(predictions[good].mean()) if good.any() else None,
              "latency_ms": float(latency.mean()), "unavailable": {}}
    if result["image_auroc"] is None:
        result["unavailable"]["image_auroc"] = "Requires both GOOD and DEFECT labels"
    if masks is None or maps is None or any(m is None for m in masks):
        result["unavailable"]["pixel_auroc"] = "Ground truth mask unavailable"
    else:
        if len(masks) != len(labels) or len(maps) != len(labels):
            raise ValueError("One mask and anomaly map required per image")
        if any(np.asarray(m).shape != np.asarray(a).shape for m, a in zip(masks, maps)):
            raise ValueError("Masks and maps must share geometry")
        pixels = np.concatenate([np.asarray(m).ravel() for m in masks])
        values = np.concatenate([np.asarray(a).ravel() for a in maps])
        if not np.isin(pixels, [0, 1]).all() or not np.isfinite(values).all():
            raise ValueError("Invalid pixel labels/maps")
        if len(np.unique(pixels)) == 2:
            result["pixel_auroc"] = float(roc_auc_score(pixels, values))
        else:
            result["unavailable"]["pixel_auroc"] = "Requires normal and anomalous pixels"
    for key, available in (("false_accept_rate", defects.any()), ("false_reject_rate", good.any())):
        if not available:
            result["unavailable"][key] = "Required class absent"
    return result
