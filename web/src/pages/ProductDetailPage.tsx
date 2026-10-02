import React, { useEffect, useState, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { ArrowLeft, Upload, Trash2, SlidersHorizontal } from 'lucide-react';
import {
  getProduct, updateThreshold, uploadReferenceImage,
  getReferenceImages, deleteReferenceImage
} from '../api/products';
import { getInspections } from '../api/inspections';
import type { Product, ReferenceImage, InspectionListItem } from '../types';
import { DecisionBadge } from '../components/common/DecisionBadge';

const modelStatusLabel: Record<string, string> = {
  not_available: 'Preparing',
  training: 'Training',
  ready: 'Ready',
  validation_required: 'Validating',
};
const modelStatusColor: Record<string, string> = {
  not_available: 'text-vqc-muted',
  training: 'text-yellow-400',
  ready: 'text-vqc-pass',
  validation_required: 'text-vqc-review',
};

export const ProductDetailPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [product, setProduct] = useState<Product | null>(null);
  const [images, setImages] = useState<ReferenceImage[]>([]);
  const [inspections, setInspections] = useState<InspectionListItem[]>([]);
  const [threshold, setThreshold] = useState(0.55);
  const [saving, setSaving] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [loading, setLoading] = useState(true);

  const load = async () => {
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
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, [id]);

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
    try {
      for (const file of files) {
        await uploadReferenceImage(id, file);
      }
      load();
    } finally {
      setUploading(false);
      e.target.value = '';
    }
  };

  const handleDeleteImage = async (imageId: string) => {
    if (!id) return;
    await deleteReferenceImage(id, imageId);
    load();
  };

  if (loading) return <div className="flex justify-center py-16"><div className="spinner w-8 h-8" /></div>;
  if (!product) return <div className="text-vqc-muted">Product not found.</div>;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center gap-4">
        <button onClick={() => navigate('/products')} className="btn-secondary p-2">
          <ArrowLeft className="w-4 h-4" />
        </button>
        <div>
          <h1 className="text-2xl font-bold text-vqc-text">{product.name}</h1>
          <p className="text-vqc-muted text-sm font-mono">{product.code}</p>
        </div>
        <div className="ml-auto">
          <span className={`text-sm font-medium ${modelStatusColor[product.model_status]}`}>
            Model Profile: {modelStatusLabel[product.model_status]}
          </span>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left: settings */}
        <div className="space-y-4">
          {/* Product info */}
          <div className="card">
            <h3 className="section-title">Product Information</h3>
            {product.description && (
              <p className="text-vqc-muted text-sm mb-3">{product.description}</p>
            )}
            <div className="space-y-2 text-sm">
              <div className="flex justify-between">
                <span className="text-vqc-muted">Reference Images</span>
                <span className="text-vqc-text font-semibold">{product.reference_image_count} / 30</span>
              </div>
              <div className="bg-vqc-border rounded-full h-1.5">
                <div
                  className="bg-vqc-accent h-1.5 rounded-full"
                  style={{ width: `${Math.min(product.reference_image_count / 30 * 100, 100)}%` }}
                />
              </div>
              <p className="text-vqc-muted text-xs">Upload 20–30 good reference images for training</p>
            </div>
          </div>

          {/* Threshold */}
          <div className="card">
            <div className="flex items-center gap-2 mb-3">
              <SlidersHorizontal className="w-4 h-4 text-vqc-accent" />
              <h3 className="text-sm font-semibold text-vqc-text">Inspection Threshold</h3>
            </div>
            <div className="mb-2 flex justify-between">
              <span className="text-vqc-muted text-xs">Sensitivity</span>
              <span className="text-vqc-text font-bold text-sm">{(threshold * 100).toFixed(0)}%</span>
            </div>
            <input
              type="range" min={0.1} max={0.95} step={0.05}
              value={threshold} className="w-full accent-vqc-accent mb-3"
              onChange={e => setThreshold(Number(e.target.value))}
            />
            <div className="flex justify-between text-xs text-vqc-muted mb-4">
              <span>Strict</span><span>Lenient</span>
            </div>
            <button
              onClick={handleThresholdSave}
              disabled={saving || threshold === product.threshold}
              className="btn-primary w-full"
            >
              {saving ? 'Saving...' : 'Save Threshold'}
            </button>
          </div>
        </div>

        {/* Right: Reference images */}
        <div className="lg:col-span-2 space-y-4">
          <div className="card">
            <div className="flex items-center justify-between mb-4">
              <h3 className="section-title mb-0">
                Reference Images ({images.length})
              </h3>
              <button
                onClick={() => fileInputRef.current?.click()}
                disabled={uploading}
                className="btn-secondary flex items-center gap-2 text-xs"
              >
                <Upload className="w-3.5 h-3.5" />
                {uploading ? 'Uploading...' : 'Upload Images'}
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

            {images.length === 0 ? (
              <div className="border-2 border-dashed border-vqc-border rounded-lg p-8 text-center">
                <Upload className="w-8 h-8 mx-auto mb-2 text-vqc-muted opacity-40" />
                <p className="text-vqc-muted text-sm">Upload 20–30 GOOD reference images of this product.</p>
                <p className="text-vqc-muted text-xs mt-1">These will be used for quality profile training.</p>
              </div>
            ) : (
              <div className="grid grid-cols-3 sm:grid-cols-4 lg:grid-cols-5 gap-2">
                {images.map(img => (
                  <div key={img.id} className="relative group aspect-square rounded-lg overflow-hidden bg-vqc-panel">
                    <img
                      src={img.storage_url}
                      alt="Reference"
                      className="w-full h-full object-cover"
                    />
                    <div className="absolute inset-0 bg-black/60 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center">
                      <button
                        onClick={() => handleDeleteImage(img.id)}
                        className="w-8 h-8 bg-red-500/80 rounded-full flex items-center justify-center"
                      >
                        <Trash2 className="w-3.5 h-3.5 text-white" />
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Recent inspections for this product */}
          <div className="card">
            <h3 className="section-title">Recent Inspections</h3>
            {inspections.length === 0 ? (
              <p className="text-vqc-muted text-sm text-center py-4">No inspections yet for this product.</p>
            ) : (
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-vqc-border">
                    {['Time', 'Decision', 'Score', 'Time (ms)'].map(h => (
                      <th key={h} className="text-left text-vqc-muted font-medium py-2 px-2 text-xs uppercase">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {inspections.map(insp => (
                    <tr key={insp.inspection_id} className="border-b border-vqc-border/50 hover:bg-vqc-panel/50">
                      <td className="py-2 px-2 text-vqc-muted text-xs font-mono">
                        {new Date(insp.created_at).toLocaleString()}
                      </td>
                      <td className="py-2 px-2">
                        <DecisionBadge decision={insp.decision} size="sm" />
                      </td>
                      <td className="py-2 px-2 font-mono text-xs">{(insp.anomaly_score * 100).toFixed(1)}%</td>
                      <td className="py-2 px-2 text-vqc-muted font-mono text-xs">{insp.processing_time_ms}ms</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
