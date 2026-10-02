import React, { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Plus, Package, ScanLine, ChevronRight, Trash2 } from 'lucide-react';
import { getProducts, createProduct, deleteProduct } from '../api/products';
import type { Product, ProductCreate } from '../types';

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
      await createProduct(form);
      setShowCreate(false);
      setForm({ name: '', code: '', description: '', threshold: 0.55 });
      load();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setCreating(false);
    }
  };

  const handleDelete = async (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!confirm('Delete this product?')) return;
    await deleteProduct(id);
    load();
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-vqc-text">Products</h1>
          <p className="text-vqc-muted text-sm mt-1">Manage product profiles and inspection thresholds</p>
        </div>
        <button onClick={() => setShowCreate(true)} className="btn-primary flex items-center gap-2">
          <Plus className="w-4 h-4" /> New Product
        </button>
      </div>

      {/* Create modal */}
      {showCreate && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4">
          <div className="card w-full max-w-lg">
            <h2 className="text-lg font-semibold text-vqc-text mb-4">New Product</h2>
            {error && <p className="text-red-400 text-sm mb-4">{error}</p>}
            <form onSubmit={handleCreate} className="space-y-4">
              <div>
                <label className="label">Product Name *</label>
                <input className="input" required value={form.name}
                  onChange={e => setForm(f => ({ ...f, name: e.target.value }))} />
              </div>
              <div>
                <label className="label">Product Code *</label>
                <input className="input" required value={form.code}
                  onChange={e => setForm(f => ({ ...f, code: e.target.value }))}
                  placeholder="e.g. SCR-M8-001" />
              </div>
              <div>
                <label className="label">Description</label>
                <textarea className="input min-h-[80px] resize-none" value={form.description || ''}
                  onChange={e => setForm(f => ({ ...f, description: e.target.value }))} />
              </div>
              <div>
                <label className="label">
                  Inspection Threshold: {(form.threshold * 100).toFixed(0)}%
                </label>
                <input type="range" min={0.1} max={0.95} step={0.05}
                  value={form.threshold} className="w-full accent-vqc-accent"
                  onChange={e => setForm(f => ({ ...f, threshold: Number(e.target.value) }))} />
                <div className="flex justify-between text-xs text-vqc-muted mt-1">
                  <span>Strict (10%)</span><span>Lenient (95%)</span>
                </div>
              </div>
              <div className="flex gap-3 pt-2">
                <button type="submit" disabled={creating} className="btn-primary flex-1">
                  {creating ? 'Creating...' : 'Create Product'}
                </button>
                <button type="button" onClick={() => setShowCreate(false)} className="btn-secondary flex-1">
                  Cancel
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Product list */}
      {loading ? (
        <div className="flex justify-center py-12"><div className="spinner w-8 h-8" /></div>
      ) : products.length === 0 ? (
        <div className="card text-center py-12">
          <Package className="w-12 h-12 mx-auto mb-4 text-vqc-muted opacity-40" />
          <p className="text-vqc-muted">No products yet. Create your first product profile.</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-4">
          {products.map(product => (
            <div
              key={product.id}
              className="card cursor-pointer hover:border-vqc-accent/50 transition-colors"
              onClick={() => navigate(`/products/${product.id}`)}
            >
              <div className="flex items-start justify-between mb-3">
                <div>
                  <h3 className="font-semibold text-vqc-text">{product.name}</h3>
                  <p className="text-vqc-muted text-xs font-mono mt-0.5">{product.code}</p>
                </div>
                <div className="flex items-center gap-2">
                  <button
                    onClick={e => handleDelete(product.id, e)}
                    className="w-7 h-7 flex items-center justify-center rounded hover:bg-red-500/20 text-vqc-muted hover:text-red-400 transition-colors"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                  <ChevronRight className="w-4 h-4 text-vqc-muted" />
                </div>
              </div>
              <div className="grid grid-cols-2 gap-3 text-sm">
                <div>
                  <span className="label">Threshold</span>
                  <span className="text-vqc-text font-semibold">{(product.threshold * 100).toFixed(0)}%</span>
                </div>
                <div>
                  <span className="label">Reference Images</span>
                  <span className="text-vqc-text font-semibold">{product.reference_image_count}</span>
                </div>
                <div className="col-span-2">
                  <span className="label">Model Profile</span>
                  <span className={`text-sm font-medium ${modelStatusColor[product.model_status]}`}>
                    {modelStatusLabel[product.model_status]}
                  </span>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};
