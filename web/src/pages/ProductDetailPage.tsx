import React, { useEffect, useState, useRef, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  ArrowLeft, Upload, Trash2, SlidersHorizontal, Brain,
  CheckCircle, AlertTriangle, Loader, Camera, ScanLine,
  Images, X, Plus,
} from 'lucide-react';
import Webcam from 'react-webcam';
import {
  getProduct, updateThreshold, uploadReferenceImage,
  getReferenceImages, deleteReferenceImage,
  startLearnNormal, getLearnNormalStatus,
} from '../api/products';
import type { LearnNormalStatus } from '../api/products';
import { getInspections } from '../api/inspections';
import type { Product, ReferenceImage, InspectionListItem } from '../types';
import { DecisionBadge } from '../components/common/DecisionBadge';

const MIN_IMAGES = 20;
const MAX_IMAGES = 30;

/* ── helpers ─────────────────────────────────── */
function getStatusLabel(status: string, refCount: number): string {
  if (status === 'ready') return 'Ready for Inspection';
  if (status === 'training') return 'Learning Normal…';
  if (status === 'validation_required') return 'Validation Required';
  if (refCount >= MIN_IMAGES) return 'Ready to Learn';
  return 'Collecting References';
}

function getStatusColor(status: string, refCount: number): string {
  if (status === 'ready') return 'text-vqc-pass';
  if (status === 'training') return 'text-yellow-400';
  if (status === 'validation_required') return 'text-vqc-review';
  if (refCount >= MIN_IMAGES) return 'text-vqc-accent';
  return 'text-vqc-muted';
}

function ProgressBar({ value, max }: { value: number; max: number }) {
  const pct = Math.min((value / max) * 100, 100);
  return (
    <div className="w-full bg-vqc-border rounded-full h-2.5 overflow-hidden">
      <div
        className={`h-2.5 rounded-full transition-all duration-500 ${value >= MIN_IMAGES ? 'bg-vqc-pass' : 'bg-vqc-accent'}`}
        style={{ width: `${pct}%` }}
      />
    </div>
  );
}

/* ── Training status banner ─────────────────── */
function TrainingBanner({
  status,
  productId,
  onDismiss,
}: {
  status: string;
  productId: string;
  onDismiss: () => void;
}) {
  const navigate = useNavigate();
  if (status === 'training') {
    return (
      <div className="flex items-center gap-3 bg-yellow-500/10 border border-yellow-500/30 rounded-xl px-4 py-4">
        <Loader className="w-5 h-5 text-yellow-400 animate-spin shrink-0" />
        <div className="flex-1">
          <p className="text-yellow-300 font-semibold">Learning Normal — in progress</p>
          <p className="text-yellow-200/60 text-xs mt-0.5">
            Your reference images are being processed. This usually takes 30–60 seconds.
            Status updates automatically.
          </p>
        </div>
      </div>
    );
  }
  if (status === 'ready') {
    return (
      <div className="flex items-center gap-4 bg-green-500/10 border border-green-500/30 rounded-xl px-4 py-4">
        <CheckCircle className="w-5 h-5 text-green-400 shrink-0" />
        <div className="flex-1">
          <p className="text-green-300 font-semibold">Ready for Inspection!</p>
          <p className="text-green-200/60 text-xs mt-0.5">
            The product profile has been trained. You can now inspect units.
          </p>
        </div>
        <button
          onClick={() => navigate(`/inspect?product=${productId}`)}
          className="btn-primary text-xs shrink-0 flex items-center gap-1.5"
        >
          <ScanLine className="w-3.5 h-3.5" /> Inspect Now
        </button>
        <button onClick={onDismiss} className="text-green-400/50 hover:text-green-300 transition-colors ml-1">
          <X className="w-4 h-4" />
        </button>
      </div>
    );
  }
  if (status === 'validation_required') {
    return (
      <div className="flex items-center gap-3 bg-amber-500/10 border border-amber-500/30 rounded-xl px-4 py-4">
        <AlertTriangle className="w-5 h-5 text-amber-400 shrink-0" />
        <div className="flex-1">
          <p className="text-amber-300 font-semibold">Profile requires validation</p>
          <p className="text-amber-200/60 text-xs mt-0.5">
            Training completed but automatic binding could not be confirmed. Contact your administrator.
          </p>
        </div>
        <button onClick={onDismiss} className="text-amber-400/50 hover:text-amber-300">
          <X className="w-4 h-4" />
        </button>
      </div>
    );
  }
  return null;
}

/* ══════════════════════════════════════════════
   MAIN PAGE
═══════════════════════════════════════════════ */
export const ProductDetailPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const webcamRef = useRef<Webcam>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const [product, setProduct] = useState<Product | null>(null);
  const [images, setImages] = useState<ReferenceImage[]>([]);
  const [inspections, setInspections] = useState<InspectionListItem[]>([]);
  const [threshold, setThreshold] = useState(0.55);
  const [saving, setSaving] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadCount, setUploadCount] = useState(0); // tracks batch progress
  const [loading, setLoading] = useState(true);
  const [training, setTraining] = useState(false);
  const [trainError, setTrainError] = useState('');
  const [trainBanner, setTrainBanner] = useState('');
  // Webcam capture mode for reference images
  const [webcamMode, setWebcamMode] = useState(false);
  const [webcamError, setWebcamError] = useState(false);
  const [capturingRef, setCapturingRef] = useState(false);

  /* ── polling ── */
  const stopPoll = useCallback(() => {
    if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
  }, []);

  const startStatusPoll = useCallback(() => {
    if (!id || pollRef.current) return;
    pollRef.current = setInterval(async () => {
      try {
        const s: LearnNormalStatus = await getLearnNormalStatus(id);
        if (s.model_status !== 'training') {
          stopPoll();
          const p = await getProduct(id);
          setProduct(p);
          setThreshold(p.threshold);
          setTrainBanner(s.model_status);
          setTraining(false);
        }
      } catch {
        stopPoll();
        setTraining(false);
      }
    }, 3000);
  }, [id, stopPoll]);

  /* ── load ── */
  const load = useCallback(async () => {
    if (!id) return;
    try {
      const [p, imgs, insps] = await Promise.all([
        getProduct(id),
        getReferenceImages(id),
        getInspections({ product_id: id, page_size: 10 }),
      ]);
      setProduct(p);
      setThreshold(p.threshold);
      setImages(imgs);
      setInspections(insps.items);
      if (p.model_status === 'training') { setTraining(true); startStatusPoll(); }
    } finally {
      setLoading(false);
    }
  }, [id, startStatusPoll]);

  useEffect(() => { load(); return () => stopPoll(); }, [id]);

  /* ── actions ── */
  const handleLearnNormal = async () => {
    if (!id) return;
    setTrainError('');
    setTraining(true);
    try {
      await startLearnNormal(id);
      setTrainBanner('training');
      const p = await getProduct(id);
      setProduct(p);
      setThreshold(p.threshold);
      startStatusPoll();
    } catch (error: unknown) {
      const detail = (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setTrainError(detail || (error instanceof Error ? error.message : 'Could not start training.'));
      setTraining(false);
    }
  };

  const handleThresholdSave = async () => {
    if (!id) return;
    setSaving(true);
    try {
      const updated = await updateThreshold(id, threshold);
      setProduct(updated);
    } finally {
      setSaving(false);
    }
  };

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files || []);
    if (!id || files.length === 0) return;
    setUploading(true);
    setUploadCount(0);
    try {
      for (let i = 0; i < files.length; i++) {
        await uploadReferenceImage(id, files[i]);
        setUploadCount(i + 1);
      }
      await load();
    } finally {
      setUploading(false);
      setUploadCount(0);
      e.target.value = '';
    }
  };

  const handleCaptureRef = useCallback(async () => {
    if (!id || !webcamRef.current) return;
    const screenshot = webcamRef.current.getScreenshot();
    if (!screenshot) return;
    setCapturingRef(true);
    try {
      const blob = await (await fetch(screenshot)).blob();
      const file = new File([blob], `ref_${Date.now()}.jpg`, { type: 'image/jpeg' });
      await uploadReferenceImage(id, file);
      await load();
    } finally {
      setCapturingRef(false);
    }
  }, [id, load]);

  const handleDeleteImage = async (imageId: string) => {
    if (!id) return;
    if (!confirm('Remove this reference image?')) return;
    await deleteReferenceImage(id, imageId);
    load();
  };

  /* ── loading / not found ── */
  if (loading) {
    return <div className="flex justify-center py-16"><div className="spinner w-8 h-8" /></div>;
  }
  if (!product) {
    return <div className="text-vqc-muted text-center py-16">Product not found.</div>;
  }

  const refCount = product.reference_image_count || 0;
  const canTrain = refCount >= MIN_IMAGES && product.model_status !== 'training' && product.model_status !== 'ready';
  const isReady = product.model_status === 'ready';

  return (
    <div className="space-y-6">
      {/* Training status banner */}
      {trainBanner && (
        <TrainingBanner
          status={trainBanner}
          productId={product.id}
          onDismiss={() => setTrainBanner('')}
        />
      )}

      {/* ── Header ── */}
      <div className="flex items-center gap-4">
        <button onClick={() => navigate('/products')} className="btn-secondary p-2">
          <ArrowLeft className="w-4 h-4" />
        </button>
        <div className="flex-1 min-w-0">
          <h1 className="text-2xl font-bold text-vqc-text truncate">{product.name}</h1>
          <p className="text-vqc-muted text-sm font-mono">{product.code}</p>
        </div>
        <div className="shrink-0">
          <span className={`text-sm font-semibold ${getStatusColor(product.model_status, refCount)}`}>
            {getStatusLabel(product.model_status, refCount)}
          </span>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* ── LEFT: Learn Normal + Threshold ── */}
        <div className="space-y-4">

          {/* ════════════════════════════════
              LEARN NORMAL CARD (prominent)
          ════════════════════════════════ */}
          <div className={`card border-2 ${
            isReady
              ? 'border-green-500/40 bg-green-500/5'
              : refCount >= MIN_IMAGES
              ? 'border-vqc-accent/40'
              : 'border-vqc-border'
          }`}>
            {/* Section title */}
            <div className="flex items-center gap-2 mb-1">
              <Brain className={`w-5 h-5 ${isReady ? 'text-vqc-pass' : 'text-vqc-accent'}`} />
              <h2 className="text-base font-bold text-vqc-text">Learn Normal</h2>
            </div>
            <p className="text-vqc-muted text-xs mb-4 leading-relaxed">
              Add <strong className="text-vqc-text">20–30 photos of GOOD units</strong> — only
              defect-free examples — so the system learns what this product normally looks like.
              Then click <strong className="text-vqc-text">Learn Normal</strong> to train.
            </p>

            {/* Reference image counter */}
            <div className="mb-1 flex justify-between items-center">
              <span className="text-xs text-vqc-muted font-semibold uppercase tracking-wide">GOOD Reference Images</span>
              <span className={`text-sm font-bold tabular-nums ${refCount >= MIN_IMAGES ? 'text-vqc-pass' : refCount > 0 ? 'text-vqc-text' : 'text-vqc-muted'}`}>
                {refCount} / {MIN_IMAGES}
                {refCount > MIN_IMAGES && refCount <= MAX_IMAGES && (
                  <span className="text-vqc-muted font-normal text-xs ml-1">(great!)</span>
                )}
              </span>
            </div>
            <ProgressBar value={refCount} max={MAX_IMAGES} />

            {/* Contextual hint */}
            <div className="mt-2 mb-4 min-h-[18px]">
              {isReady ? (
                <p className="text-vqc-pass text-xs font-medium flex items-center gap-1">
                  <CheckCircle className="w-3.5 h-3.5" /> Profile is trained and active
                </p>
              ) : product.model_status === 'training' ? (
                <p className="text-yellow-400 text-xs font-medium flex items-center gap-1">
                  <Loader className="w-3.5 h-3.5 animate-spin" /> Training in progress…
                </p>
              ) : refCount >= MIN_IMAGES ? (
                <p className="text-vqc-accent text-xs font-medium">
                  ✓ {refCount >= MIN_IMAGES ? 'Minimum reached' : ''} — ready to start training
                </p>
              ) : (
                <p className="text-vqc-muted text-xs">
                  Need <strong className="text-vqc-text">{MIN_IMAGES - refCount}</strong> more image{MIN_IMAGES - refCount !== 1 ? 's' : ''} to begin
                </p>
              )}
            </div>

            {/* Learn Normal button */}
            {!isReady && (
              <>
                <button
                  id="learn-normal-btn"
                  className={`w-full flex items-center justify-center gap-2 py-2.5 rounded-lg font-semibold text-sm transition-all duration-150 ${
                    canTrain && !training
                      ? 'bg-vqc-accent hover:bg-blue-500 text-white shadow-lg shadow-cyan-500/20'
                      : 'bg-vqc-panel text-vqc-muted border border-vqc-border cursor-not-allowed'
                  }`}
                  disabled={!canTrain || training}
                  onClick={handleLearnNormal}
                >
                  {training ? (
                    <><Loader className="w-4 h-4 animate-spin" /> Learning Normal…</>
                  ) : (
                    <><Brain className="w-4 h-4" /> {refCount >= MIN_IMAGES ? 'Start Learning Normal' : `Add ${MIN_IMAGES - refCount} more images first`}</>
                  )}
                </button>
                {trainError && (
                  <p role="alert" className="text-red-300 text-xs mt-2">{trainError}</p>
                )}
              </>
            )}

            {/* Ready CTA */}
            {isReady && (
              <button
                onClick={() => navigate(`/inspect?product=${product.id}`)}
                className="w-full flex items-center justify-center gap-2 py-2.5 rounded-lg font-semibold text-sm bg-vqc-pass/15 hover:bg-vqc-pass/25 text-vqc-pass border border-vqc-pass/30 transition-all duration-150"
              >
                <ScanLine className="w-4 h-4" /> Inspect New Unit
              </button>
            )}
          </div>

          {/* ── Threshold ── */}
          <div className="card">
            <div className="flex items-center gap-2 mb-3">
              <SlidersHorizontal className="w-4 h-4 text-vqc-accent" />
              <h3 className="text-sm font-semibold text-vqc-text">Inspection Threshold</h3>
            </div>
            <p className="text-vqc-muted text-xs mb-3 leading-relaxed">
              Controls how sensitive inspections are. Lower = stricter (more flags). Higher = more lenient.
            </p>
            <div className="flex justify-between items-center mb-1">
              <span className="text-vqc-muted text-xs">Strict ← → Lenient</span>
              <span className="text-vqc-text font-bold text-base tabular-nums">
                {(threshold * 100).toFixed(0)}%
              </span>
            </div>
            <input
              type="range" min={0.1} max={0.95} step={0.05}
              value={threshold}
              className="w-full accent-vqc-accent mb-3"
              onChange={e => setThreshold(Number(e.target.value))}
            />
            <div className="flex justify-between text-xs text-vqc-muted mb-4">
              <span>10% (Strict)</span>
              <span>95% (Lenient)</span>
            </div>
            <button
              onClick={handleThresholdSave}
              disabled={saving || threshold === product.threshold}
              className="btn-primary w-full"
            >
              {saving ? 'Saving…' : 'Save Threshold'}
            </button>
          </div>
        </div>

        {/* ── RIGHT: Reference image gallery ── */}
        <div className="lg:col-span-2 space-y-4">

          {/* Reference images card */}
          <div className="card">
            {/* Header */}
            <div className="flex items-center justify-between mb-1">
              <div className="flex items-center gap-2">
                <Images className="w-4 h-4 text-vqc-accent" />
                <h3 className="section-title mb-0">
                  GOOD Reference Images
                  <span className="text-vqc-muted font-normal ml-2 text-xs">
                    ({refCount} uploaded · 20 required · up to 30 recommended)
                  </span>
                </h3>
              </div>
            </div>
            <p className="text-vqc-muted text-xs mb-4">
              Only upload photos of <strong className="text-vqc-text">normal, defect-free units</strong>.
              These teach the system what "good" looks like. Wrong images will reduce accuracy.
            </p>

            {/* Upload/Camera actions */}
            {!isReady && (
              <div className="flex gap-2 mb-4">
                <button
                  onClick={() => fileInputRef.current?.click()}
                  disabled={uploading}
                  className="btn-primary flex items-center gap-2 flex-1"
                >
                  <Upload className="w-3.5 h-3.5" />
                  {uploading
                    ? `Uploading ${uploadCount}…`
                    : 'Upload GOOD Images'}
                </button>
                <button
                  onClick={() => { setWebcamMode(m => !m); setWebcamError(false); }}
                  className={`btn-secondary flex items-center gap-2 ${webcamMode ? 'border-vqc-accent text-vqc-accent' : ''}`}
                >
                  <Camera className="w-3.5 h-3.5" />
                  {webcamMode ? 'Close Camera' : 'Capture with Camera'}
                </button>
                <input
                  ref={fileInputRef}
                  type="file"
                  multiple
                  accept="image/jpeg,image/png,image/webp"
                  className="hidden"
                  onChange={handleUpload}
                />
              </div>
            )}

            {/* Webcam capture panel */}
            {webcamMode && (
              <div className="mb-4 bg-vqc-panel border border-vqc-border rounded-xl overflow-hidden">
                <div className="aspect-video relative">
                  {webcamError ? (
                    <div className="flex flex-col items-center justify-center h-full gap-2 text-vqc-muted">
                      <Camera className="w-10 h-10 opacity-30" />
                      <p className="text-sm">Camera unavailable. Use file upload instead.</p>
                    </div>
                  ) : (
                    <Webcam
                      ref={webcamRef}
                      screenshotFormat="image/jpeg"
                      className="w-full h-full object-cover"
                      onUserMediaError={() => setWebcamError(true)}
                    />
                  )}
                </div>
                {!webcamError && (
                  <div className="p-3 flex gap-2">
                    <button
                      onClick={handleCaptureRef}
                      disabled={capturingRef}
                      className="btn-primary flex items-center gap-2 flex-1"
                    >
                      {capturingRef
                        ? <><Loader className="w-3.5 h-3.5 animate-spin" /> Saving…</>
                        : <><Camera className="w-3.5 h-3.5" /> Capture GOOD Image</>
                      }
                    </button>
                    <button
                      onClick={() => setWebcamMode(false)}
                      className="btn-secondary flex items-center gap-2"
                    >
                      <X className="w-3.5 h-3.5" /> Done
                    </button>
                  </div>
                )}
              </div>
            )}

            {/* Gallery or empty state */}
            {images.length === 0 ? (
              <div
                className="border-2 border-dashed border-vqc-border rounded-xl p-10 text-center cursor-pointer hover:border-vqc-accent/50 transition-colors"
                onClick={() => fileInputRef.current?.click()}
              >
                <Upload className="w-10 h-10 mx-auto mb-3 text-vqc-muted opacity-30" />
                <p className="text-vqc-text font-medium">Upload GOOD Reference Images</p>
                <p className="text-vqc-muted text-sm mt-1">
                  Drag photos here or click to select — you need at least {MIN_IMAGES}
                </p>
                <p className="text-vqc-muted text-xs mt-1">JPG, PNG, WEBP · Multiple selection supported</p>
              </div>
            ) : (
              <div className="grid grid-cols-3 sm:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-2">
                {/* Add more tile */}
                {!isReady && (
                  <div
                    className="aspect-square rounded-lg overflow-hidden bg-vqc-panel border-2 border-dashed border-vqc-border flex flex-col items-center justify-center cursor-pointer hover:border-vqc-accent/50 transition-colors"
                    onClick={() => fileInputRef.current?.click()}
                  >
                    <Plus className="w-5 h-5 text-vqc-muted" />
                    <span className="text-vqc-muted text-xs mt-1">Add</span>
                  </div>
                )}
                {images.map(img => (
                  <div key={img.id} className="relative group aspect-square rounded-lg overflow-hidden bg-vqc-panel border border-vqc-border/50">
                    <img
                      src={img.storage_url}
                      alt="GOOD reference"
                      className="w-full h-full object-cover"
                    />
                    {!isReady && (
                      <div className="absolute inset-0 bg-black/60 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center">
                        <button
                          onClick={() => handleDeleteImage(img.id)}
                          className="w-8 h-8 bg-red-500/80 rounded-full flex items-center justify-center hover:bg-red-500 transition-colors"
                          title="Remove reference image"
                        >
                          <Trash2 className="w-3.5 h-3.5 text-white" />
                        </button>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}

            {/* Progress summary below gallery */}
            {images.length > 0 && !isReady && (
              <div className="mt-3 pt-3 border-t border-vqc-border/50">
                <div className="flex items-center justify-between mb-1.5">
                  <span className="text-vqc-muted text-xs">Progress toward training</span>
                  <span className={`text-xs font-bold ${refCount >= MIN_IMAGES ? 'text-vqc-pass' : 'text-vqc-text'}`}>
                    {refCount} / {MIN_IMAGES} minimum
                  </span>
                </div>
                <ProgressBar value={refCount} max={MAX_IMAGES} />
              </div>
            )}
          </div>

          {/* Recent inspections */}
          {inspections.length > 0 && (
            <div className="card">
              <h3 className="section-title">Recent Inspections</h3>
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-vqc-border">
                    {['Time', 'Decision', 'Score', 'Threshold', 'Duration'].map(h => (
                      <th key={h} className="text-left text-vqc-muted font-medium py-2 px-2 text-xs uppercase">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {inspections.map(insp => (
                    <tr key={insp.inspection_id} className="border-b border-vqc-border/50 hover:bg-vqc-panel/50 transition-colors">
                      <td className="py-2 px-2 text-vqc-muted text-xs font-mono">
                        {new Date(insp.created_at).toLocaleString()}
                      </td>
                      <td className="py-2 px-2">
                        <DecisionBadge decision={insp.decision} size="sm" />
                      </td>
                      <td className="py-2 px-2 font-mono text-xs">{insp.anomaly_score.toFixed(3)}</td>
                      <td className="py-2 px-2 font-mono text-xs text-vqc-muted">
                        {insp.threshold != null ? insp.threshold.toFixed(2) : '—'}
                      </td>
                      <td className="py-2 px-2 text-vqc-muted font-mono text-xs">{insp.processing_time_ms}ms</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {/* Empty inspections state */}
          {inspections.length === 0 && isReady && (
            <div className="card text-center py-8">
              <ScanLine className="w-8 h-8 mx-auto mb-3 text-vqc-muted opacity-30" />
              <p className="text-vqc-text font-medium">No inspections yet</p>
              <p className="text-vqc-muted text-sm mt-1">Run your first inspection for this product.</p>
              <button
                onClick={() => navigate(`/inspect?product=${product.id}`)}
                className="btn-primary mt-4 inline-flex items-center gap-2"
              >
                <ScanLine className="w-3.5 h-3.5" /> Inspect Now
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
