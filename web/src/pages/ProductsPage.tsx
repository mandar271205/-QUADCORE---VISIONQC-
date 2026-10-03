import React, { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Plus, Package, ChevronRight, Trash2, Brain, CheckCircle, Clock } from 'lucide-react';
import { getProducts, createProduct, deleteProduct } from '../api/products';
import type { Product, ProductCreate } from '../types';

const modelStatusLabel: Record<string, string> = {
  not_available: 'Collecting References',
  training: 'Learning Normal…',
  ready: 'Ready',
  validation_required: 'Validating',
};

const modelStatusColor: Record<string, string> = {
  not_available: 'text-vqc-muted',
  training: 'text-yellow-400',
  ready: 'text-vqc-pass',
  validation_required: 'text-vqc-review',
};

const MIN_IMAGES = 20;

function getCardStatusLabel(product: Product): string {
  if (product.model_status === 'ready') return 'Ready';
  if (product.model_status === 'training') return 'Learning Normal…';
  if (product.model_status === 'validation_required') return 'Validating';
  if ((product.reference_image_count || 0) >= MIN_IMAGES) return 'Ready to Learn';
  return `Collecting (${product.reference_image_count || 0} / ${MIN_IMAGES})`;
}

function getCardStatusColor(product: Product): string {
  if (product.model_status === 'ready') return 'text-vqc-pass';
  if (product.model_status === 'training') return 'text-yellow-400';
  if (product.model_status === 'validation_required') return 'text-vqc-review';
  if ((product.reference_image_count || 0) >= MIN_IMAGES) return 'text-vqc-accent';
  return 'text-vqc-muted';
}

export const ProductsPage: React.FC = () => {
  const navigate = useNavigate();
  const [products, setProducts] = useState<Product[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [form, setForm] = useState<ProductCreate>({
    name: '', code: '', description: '', threshold: 0.55
  });
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState('');

  const load = async () => {
    try {
      const p = await getProducts();
      setProducts(p);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    setCreating(true);
    setError('');
    try {
      const created = await createProduct(form);
      setShowCreate(false);
      setForm({ name: '', code: '', description: '', threshold: 0.55 });
      // Navigate directly to product detail so user immediately sees the
      // Learn Normal onboarding section.
      navigate(`/products/${created.id}`);
    } catch (e: any) {
      setError(e.message || 'Could not create product.');
    } finally {
      setCreating(false);
    }
  };

  const handleDelete = async (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!confirm('Delete this product and all its reference images?')) return;
    await deleteProduct(id);
    load();
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-vqc-text">Products</h1>
          <p className="text-vqc-muted text-sm mt-1">
            Create product profiles and train them on GOOD reference images
          </p>
        </div>
        <button onClick={() => setShowCreate(true)} className="btn-primary flex items-center gap-2">
          <Plus className="w-4 h-4" /> New Product
        </button>
      </div>

      {/* ── Create Product Modal ── */}
      {showCreate && (
        <div
          className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-4"
          onClick={(e) => { if (e.target === e.currentTarget) setShowCreate(false); }}
        >
          <div className="bg-vqc-surface border border-vqc-border rounded-xl w-full max-w-lg shadow-2xl">
            {/* Modal header */}
            <div className="flex items-center gap-3 px-6 pt-6 pb-4 border-b border-vqc-border">
              <div className="w-8 h-8 rounded-lg bg-vqc-accent/15 flex items-center justify-center">
                <Package className="w-4 h-4 text-vqc-accent" />
              </div>
              <div>
                <h2 className="text-base font-semibold text-vqc-text">New Product Profile</h2>
                <p className="text-vqc-muted text-xs">
                  After creating, you'll add 20–30 GOOD reference photos to teach the system what this product looks like.
                </p>
              </div>
            </div>

            <form onSubmit={handleCreate} className="px-6 py-5 space-y-4">
              {error && (
                <div className="bg-red-500/10 border border-red-500/30 rounded-lg px-3 py-2">
                  <p className="text-red-300 text-sm">{error}</p>
                </div>
              )}

              <div>
                <label className="label" htmlFor="prod-name">Product Name *</label>
                <input
                  id="prod-name"
                  className="input"
                  required
                  placeholder="e.g. CNC Bearing Housing"
                  value={form.name}
                  onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
                />
              </div>

              <div>
                <label className="label" htmlFor="prod-code">Product Code / SKU *</label>
                <input
                  id="prod-code"
                  className="input"
                  required
                  placeholder="e.g. CNC-BEAR-420"
                  value={form.code}
                  onChange={e => setForm(f => ({ ...f, code: e.target.value }))}
                />
              </div>

              <div>
                <label className="label" htmlFor="prod-desc">Description (optional)</label>
                <textarea
                  id="prod-desc"
                  className="input min-h-[72px] resize-none"
                  placeholder="Brief description of the component and what defects to watch for…"
                  value={form.description || ''}
                  onChange={e => setForm(f => ({ ...f, description: e.target.value }))}
                />
              </div>

              <div>
                <label className="label" htmlFor="prod-threshold">
                  Inspection Sensitivity: {(form.threshold * 100).toFixed(0)}%
                  <span className="text-vqc-muted font-normal ml-2">
                    ({form.threshold < 0.4 ? 'Strict' : form.threshold > 0.6 ? 'Lenient' : 'Balanced'})
                  </span>
                </label>
                <input
                  id="prod-threshold"
                  type="range" min={0.1} max={0.95} step={0.05}
                  value={form.threshold}
                  className="w-full accent-vqc-accent mt-1"
                  onChange={e => setForm(f => ({ ...f, threshold: Number(e.target.value) }))}
                />
                <div className="flex justify-between text-xs text-vqc-muted mt-1">
                  <span>← Strict (catches more)</span>
                  <span>Lenient (fewer flags) →</span>
                </div>
              </div>

              {/* What happens next — onboarding hint */}
              <div className="bg-vqc-accent/8 border border-vqc-accent/20 rounded-lg px-4 py-3 flex items-start gap-3">
                <Brain className="w-4 h-4 text-vqc-accent mt-0.5 shrink-0" />
                <p className="text-vqc-muted text-xs leading-relaxed">
                  <span className="text-vqc-text font-medium">Next step: </span>
                  After creating, you'll be taken to the product page where you can upload
                  20–30 photos of defect-free units, then click <span className="text-vqc-text font-medium">Learn Normal</span> to
                  train the system.
                </p>
              </div>

              <div className="flex gap-3 pt-1">
                <button
                  type="submit"
                  disabled={creating}
                  className="btn-primary flex-1 flex items-center justify-center gap-2"
                >
                  {creating ? (
                    <><span className="spinner w-4 h-4" /> Creating…</>
                  ) : (
                    <><Plus className="w-4 h-4" /> Create & Set Up</>
                  )}
                </button>
                <button
                  type="button"
                  onClick={() => setShowCreate(false)}
                  className="btn-secondary flex-1"
                >
                  Cancel
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* ── Product list ── */}
      {loading ? (
        <div className="flex justify-center py-12"><div className="spinner w-8 h-8" /></div>
      ) : products.length === 0 ? (
        <div className="card text-center py-16">
          <Package className="w-12 h-12 mx-auto mb-4 text-vqc-muted opacity-30" />
          <p className="text-vqc-text font-medium">No product profiles yet</p>
          <p className="text-vqc-muted text-sm mt-1">Create your first product to get started.</p>
          <button
            onClick={() => setShowCreate(true)}
            className="btn-primary mt-5 inline-flex items-center gap-2"
          >
            <Plus className="w-4 h-4" /> New Product
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-4">
          {products.map(product => {
            const refCount = product.reference_image_count || 0;
            const refPct = Math.min((refCount / MIN_IMAGES) * 100, 100);
            const isReady = product.model_status === 'ready';
            const isTraining = product.model_status === 'training';
            const needsImages = refCount < MIN_IMAGES && !isReady && !isTraining;

            return (
              <div
                key={product.id}
                className={`card cursor-pointer transition-all duration-150 hover:border-vqc-accent/50 ${isReady ? 'border-green-500/30' : isTraining ? 'border-yellow-500/30' : ''}`}
                onClick={() => navigate(`/products/${product.id}`)}
              >
                {/* Card header */}
                <div className="flex items-start justify-between mb-3">
                  <div className="min-w-0 flex-1">
                    <h3 className="font-semibold text-vqc-text truncate">{product.name}</h3>
                    <p className="text-vqc-muted text-xs font-mono mt-0.5">{product.code}</p>
                  </div>
                  <div className="flex items-center gap-2 ml-2 shrink-0">
                    <button
                      onClick={e => handleDelete(product.id, e)}
                      className="w-7 h-7 flex items-center justify-center rounded hover:bg-red-500/20 text-vqc-muted hover:text-red-400 transition-colors"
                      title="Delete product"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                    <ChevronRight className="w-4 h-4 text-vqc-muted" />
                  </div>
                </div>

                {/* Status row */}
                <div className="flex items-center gap-2 mb-3">
                  {isReady && <CheckCircle className="w-3.5 h-3.5 text-vqc-pass shrink-0" />}
                  {isTraining && <div className="spinner w-3.5 h-3.5 shrink-0" />}
                  <span className={`text-xs font-semibold ${getCardStatusColor(product)}`}>
                    {getCardStatusLabel(product)}
                  </span>
                </div>

                {/* Reference progress bar (hidden once ready) */}
                {!isReady && (
                  <div className="mb-3">
                    <div className="flex justify-between text-xs mb-1">
                      <span className="text-vqc-muted">GOOD Reference Images</span>
                      <span className={refCount >= MIN_IMAGES ? 'text-vqc-pass font-semibold' : 'text-vqc-text'}>
                        {refCount} / {MIN_IMAGES}
                      </span>
                    </div>
                    <div className="w-full bg-vqc-border rounded-full h-1.5 overflow-hidden">
                      <div
                        className={`h-1.5 rounded-full transition-all duration-500 ${refCount >= MIN_IMAGES ? 'bg-vqc-pass' : 'bg-vqc-accent'}`}
                        style={{ width: `${refPct}%` }}
                      />
                    </div>
                    {needsImages && (
                      <p className="text-vqc-muted text-xs mt-1">
                        Add {MIN_IMAGES - refCount} more GOOD images to enable training
                      </p>
                    )}
                  </div>
                )}

                {/* Stats row */}
                <div className="grid grid-cols-2 gap-3 text-sm">
                  <div>
                    <span className="label">Threshold</span>
                    <span className="text-vqc-text font-semibold">{(product.threshold * 100).toFixed(0)}%</span>
                  </div>
                  {isReady && (
                    <div>
                      <span className="label">References</span>
                      <span className="text-vqc-text font-semibold">{refCount}</span>
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};
