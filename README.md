# VISIONQC — AI-Powered Few-Shot Visual Quality Inspection

VisionQC is a full-stack, production-structured visual quality inspection platform built for industrial assembly lines, CNC machining, PCB manufacturing, and automated quality control.

It provides real-time automated visual inspection, defect detection, interactive anomaly heatmap overlays, multi-SKU quality calibration, historical telemetry, and a **pluggable ML Adapter architecture** allowing seamless drop-in integration of future industrial anomaly models (PatchCore, PaDiM, EfficientAD) without touching frontend code.

---

## 🏗️ Repository Architecture

```
visionqc/
├── backend/                  # FastAPI 0.111+ Python Backend
│   ├── app/
│   │   ├── api/v1/           # REST endpoints (inspections, products, analytics, health)
│   │   ├── core/             # Configuration, logging, exception handlers
│   │   ├── db/               # SQLAlchemy models (PostgreSQL & SQLite compatible)
│   │   ├── schemas/          # Pydantic v2 validation contracts
│   │   └── services/
│   │       ├── ml/           # Pluggable ML Model Adapters & Mock Engine
│   │       ├── vlm/          # Multi-tier VLM providers (Gemini, Groq, NVIDIA)
│   │       ├── heatmap/      # OpenCV anomaly map generation & blending
│   │       ├── quality_gate/ # Validation rules & confidence margins
│   │       └── storage/      # Supabase Storage & base64 local fallback
│   ├── tests/                # Automated pytest suite (health, ML adapter, products, API)
│   ├── seed.py               # Database seeder with realistic factory data
│   ├── requirements.txt      # Python dependencies
│   └── .env.example          # Environment variables template
│
├── web/                      # React 18 + Vite + Tailwind CSS Web Application
│   ├── src/
│   │   ├── api/              # Axios API clients
│   │   ├── components/       # Heatmap viewer, camera feed, stats cards, tables
│   │   ├── pages/            # Dashboard, Inspect, Products, History, Analytics, Settings
│   │   └── types/            # TypeScript type contracts
│   ├── package.json
│   └── vite.config.ts
│
├── mobile/                   # React Native + Expo 51 Mobile Application
│   ├── app/                  # Expo Router tabs (Inspect, History, Products, Analytics)
│   ├── src/                  # API client, types
│   └── package.json
│
└── docs/                     # Architecture guide & SQL setup
    ├── ARCHITECTURE.md       # ML adapter specification & routing documentation
    └── supabase_bootstrap.sql# PostgreSQL database schema & indexes
```

---

## 🚀 Quick Start Guide

### 1. Backend Setup

```bash
cd backend

# Create virtual environment (Python 3.11 recommended)
py -3.11 -m venv .venv
.\.venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure environment (works out of the box with DEMO_MODE=true)
cp .env.example .env

# Seed database with sample products and historical inspection data
python seed.py

# Start FastAPI development server
uvicorn app.main:app --reload --port 8000
```

- API Documentation: [http://localhost:8000/docs](http://localhost:8000/docs)
- Health Check: [http://localhost:8000/health](http://localhost:8000/health)

### 2. Web Frontend Setup

```bash
cd web

# Install dependencies
npm install

# Build production bundle
npm run build

# Start Vite dev server
npm run dev
```

- Access the web interface at [http://localhost:5173](http://localhost:5173)

### 3. Mobile App (Expo)

```bash
cd mobile

# Start Expo development server
npx expo start
```

---

## 🧠 Pluggable ML Engine

VisionQC features an adapter layer (`app/services/ml/base.py`) separating the inspection routing from the underlying vision model:
- **`MockMLEngine`**: Available only with explicit `DEMO_MODE=true` for synthetic demonstrations. Unavailable real engines do not silently return demo results.
- **`BaseMLEngine`**: Shared adapter used by saved Autoencoder, PaDiM, PatchCore and ensemble profiles.
- **Compatible inspection responses**: Saved profiles use the existing inspection response. Product profile attachment and experiment comparison APIs provide the new administration and reporting screens.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for full implementation details.

### Member 2 ML baselines

Autoencoder and Anomalib PaDiM training, shared MVTec subset manifests, fair
comparison exports, saved backend profiles, and optional ROI experiments are
available. See [the Member 2 runbook](docs/MEMBER2_ML.md) for setup, Member 1's
PatchCore handoff contract, commands, and the remaining real-data requirements.

The expanded real-data workflow downloads the categories linked in the training
plan and selects parameters and thresholds using development F2. See
[the F2 training runbook](docs/TRAINING_F2.md) for cleaning, frozen splits,
the separate 30-shot comparison, D2S segmentation, depth fusion, and live/final
result locations.

For the exported real models, current local ports, upload verification, and a
section-by-section 7.1–7.11 handoff, see [the deployment guide](docs/DEPLOYMENT.md).
