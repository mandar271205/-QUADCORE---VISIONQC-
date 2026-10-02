# VisionQC — Technical Architecture & ML Adapter Guide

## 1. System Overview

**VisionQC** is an enterprise-grade, few-shot visual quality inspection platform designed for high-throughput industrial manufacturing lines. It provides real-time defect grading, anomaly heatmap generation, multi-SKU tolerance calibration, and unified telemetry across web and mobile factory floor interfaces.

```
┌────────────────────────────────────────────────────────┐
│                   FACTORY CLIENTS                      │
│   Web Dashboard (React + Vite)   Mobile App (Expo RN)  │
└──────────────────────────┬─────────────────────────────┘
                           │ Multipart Image Stream / REST
                           ▼
┌────────────────────────────────────────────────────────┐
│                   FASTAPI BACKEND                      │
│   ┌────────────────────────────────────────────────┐   │
│   │             INSPECTION ROUTER                  │   │
│   │   (vlm_primary | model_primary | demo_mode)   │   │
│   └────────┬───────────────────────────────┬───────┘   │
│            ▼                               ▼           │
│   ┌─────────────────┐             ┌─────────────────┐  │
│   │   VLM ENGINES   │             │   ML ENGINES    │  │
│   │  Gemini Flash   │             │  Mock Ensemble  │  │
│   │  Groq Llama 3.2 │             │  PatchCore*     │  │
│   │  NVIDIA NIM     │             │  PaDiM*         │  │
│   └────────┬────────┘             └────────┬────────┘  │
│            ▼                               ▼           │
│   ┌────────────────────────────────────────────────┐   │
│   │                 QUALITY GATE                   │   │
│   │   Confidence Check • Bounds • Review Margin   │   │
│   └────────────────────────┬───────────────────────┘   │
│                            ▼                           │
│   ┌────────────────────────────────────────────────┐   │
│   │            HEATMAP GENERATION (OpenCV)         │   │
│   │     Jet Colormap • Gaussian Blur • Blending    │   │
│   └────────────────────────┬───────────────────────┘   │
│                            ▼                           │
│   ┌────────────────────────────────────────────────┐   │
│   │      PERSISTENCE & TELEMETRY (SQLAlchemy)      │   │
│   │  Postgres (Supabase) / SQLite • File Storage   │   │
│   └────────────────────────────────────────────────┘   │
└────────────────────────────────────────────────────────┘
* Pluggable ML Adapters
```

---

## 2. Pluggable ML Model Adapter System

One of VisionQC's core architectural tenets is **zero-frontend-change model swappability**. While production models (PatchCore, PaDiM, EfficientAD) are being trained on factory datasets, the platform runs using the `MockMLEngine` and multi-tier VLM providers.

### The `BaseMLEngine` Contract

All ML engines adhere to the strict abstract interface in `app/services/ml/base.py`:

```python
class BaseMLEngine(ABC):
    @property
    @abstractmethod
    def model_name(self) -> str:
        """Identifier for logging and audit traces."""
        ...

    @abstractmethod
    async def inspect(
        self,
        image_bytes: bytes,
        product_id: Optional[str] = None,
    ) -> MLInferenceResult:
        """
        Run inference on preprocessed tensor.
        Returns normalized anomaly score [0.0 - 1.0], confidence, 
        defects with bounding boxes, and optional 2D anomaly heatmap matrix.
        """
        ...
```

### How to Plug in a Trained PatchCore / PaDiM Model

When weights for PatchCore or EfficientAD are ready:

1. Drop model weights into `backend/models/<product_id>/patchcore.onnx` or `.pt`.
2. Create an adapter class implementing `BaseMLEngine` in `app/services/ml/patchcore_engine.py`:
   ```python
   class PatchCoreEngine(BaseMLEngine):
       def __init__(self, weights_path: str):
           # Load ONNX / TensorRT / PyTorch model
           self.session = onnxruntime.InferenceSession(weights_path)

       async def inspect(self, image_bytes: bytes, product_id: Optional[str] = None) -> MLInferenceResult:
           # 1. Preprocess image into (1, 3, 224, 224)
           # 2. Extract embedding memory patch bank
           # 3. Compute nearest neighbor distance for anomaly score
           # 4. Generate anomaly score map
           return MLInferenceResult(
               anomaly_score=score,
               confidence=0.96,
               defects=detected_clusters,
               anomaly_map=score_map_2d,
               latency_ms=inference_latency,
           )
   ```
3. Register the new engine in `MLRegistry` (`app/services/ml/registry.py`):
   ```python
   MLRegistry.register("patchcore", PatchCoreEngine(weights_path))
   ```
4. Set `INSPECTION_MODE=model_primary` and `ML_ENABLED=true` in `backend/.env`.

**No changes are required in `InspectionRouter`, API endpoints, the Web frontend, or the Mobile app!**

---

## 3. Decision Logic & Quality Gate

VisionQC implements strict quality verification before any grade is finalized:

1. **Threshold Comparison**:
   $$\text{Decision} = \begin{cases} 
   \text{FAIL} & \text{if } s > \theta + \delta \\
   \text{REVIEW} & \text{if } |s - \theta| \le \delta \\
   \text{PASS} & \text{if } s < \theta - \delta
   \end{cases}$$
   Where $s$ is the anomaly score, $\theta$ is the SKU threshold, and $\delta$ is `REVIEW_MARGIN` (default 0.05).

2. **Quality Gate Checks**:
   - **Confidence Check**: Reject inference if confidence $< 0.70$.
   - **Range Check**: Validate that $s \in [0.0, 1.0]$.
   - **Defect Consistency**: If $s > \theta$ and decision is `FAIL`, ensure at least one defect region or defect description is populated.

---

## 4. Heatmap Generation Pipeline

Heatmaps are dynamically generated in real-time by `app/services/heatmap/generator.py`:
1. Resizes or interpolates anomaly scores into a 2D intensity grid matching the input dimensions.
2. Applies OpenCV `COLORMAP_JET` (blue = nominal surface, red = severe anomaly).
3. Applies a Gaussian blur filter ($\sigma = 9$) to smooth discrete patch transitions.
4. Alpha-blends the colorized map over the original grayscale/RGB photo at 45% opacity.
5. Encodes to PNG stream for low-latency transmission.
