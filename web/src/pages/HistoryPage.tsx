import React, { useEffect, useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { Search, Filter, ChevronLeft, ChevronRight } from 'lucide-react';
import { getInspections } from '../api/inspections';
import { getProducts } from '../api/products';
import type { InspectionListItem, Product } from '../types';
import { DecisionBadge } from '../components/common/DecisionBadge';

export const HistoryPage: React.FC = () => {
  const navigate = useNavigate();
  const [items, setItems] = useState<InspectionListItem[]>([]);
  const [products, setProducts] = useState<Product[]>([]);
  const [total, setTotal] = useState(0);
  const [totalPages, setTotalPages] = useState(1);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);

  const [filters, setFilters] = useState({
    product_id: '',
    decision: '',
    date_from: '',
    date_to: '',
  });

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await getInspections({
        page,
        page_size: 20,
        ...(filters.product_id ? { product_id: filters.product_id } : {}),
        ...(filters.decision ? { decision: filters.decision } : {}),
        ...(filters.date_from ? { date_from: filters.date_from } : {}),
        ...(filters.date_to ? { date_to: filters.date_to } : {}),
      });
      setItems(res.items);
      setTotal(res.total);
      setTotalPages(res.total_pages);
    } finally {
      setLoading(false);
    }
  }, [page, filters]);

  useEffect(() => { getProducts().then(setProducts); }, []);
  useEffect(() => { load(); }, [load]);

  const handleFilterChange = (key: string, value: string) => {
    setFilters(f => ({ ...f, [key]: value }));
    setPage(1);
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-vqc-text">Inspection History</h1>
        <p className="text-vqc-muted text-sm mt-1">{total} total inspections</p>
      </div>

      {/* Filters */}
      <div className="card">
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <div>
            <label className="label">Product</label>
            <select className="input" value={filters.product_id}
              onChange={e => handleFilterChange('product_id', e.target.value)}>
              <option value="">All Products</option>
              {products.map(p => (
                <option key={p.id} value={p.id}>{p.name}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="label">Decision</label>
            <select className="input" value={filters.decision}
              onChange={e => handleFilterChange('decision', e.target.value)}>
              <option value="">All</option>
              <option value="PASS">PASS</option>
              <option value="FAIL">FAIL</option>
              <option value="REVIEW">REVIEW</option>
            </select>
          </div>
          <div>
            <label className="label">From</label>
            <input type="date" className="input" value={filters.date_from}
              onChange={e => handleFilterChange('date_from', e.target.value)} />
          </div>
          <div>
            <label className="label">To</label>
            <input type="date" className="input" value={filters.date_to}
              onChange={e => handleFilterChange('date_to', e.target.value)} />
          </div>
        </div>
      </div>

      {/* Table */}
      <div className="card">
        {loading ? (
          <div className="flex justify-center py-12"><div className="spinner w-8 h-8" /></div>
        ) : items.length === 0 ? (
          <p className="text-vqc-muted text-sm text-center py-12">No inspections found matching filters.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-vqc-border">
                  {['Timestamp', 'Product', 'Decision', 'Anomaly Score', 'Confidence', 'Time (ms)'].map(h => (
                    <th key={h} className="text-left text-vqc-muted font-medium py-3 px-3 text-xs uppercase">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {items.map(insp => (
                  <tr
                    key={insp.inspection_id}
                    className="border-b border-vqc-border/50 hover:bg-vqc-panel/50 cursor-pointer transition-colors"
                    onClick={() => navigate(`/history/${insp.inspection_id}`)}
                  >
                    <td className="py-3 px-3 text-vqc-muted text-xs font-mono">
                      {new Date(insp.created_at).toLocaleString()}
                    </td>
                    <td className="py-3 px-3 text-vqc-text">
                      {insp.product?.name ?? <span className="text-vqc-muted">—</span>}
                    </td>
                    <td className="py-3 px-3">
                      <DecisionBadge decision={insp.decision} size="sm" />
                    </td>
                    <td className="py-3 px-3 font-mono text-vqc-text">
                      {(insp.anomaly_score * 100).toFixed(1)}%
                    </td>
                    <td className="py-3 px-3 font-mono text-vqc-text">
                      {(insp.confidence * 100).toFixed(1)}%
                    </td>
                    <td className="py-3 px-3 font-mono text-vqc-muted">
                      {insp.processing_time_ms}ms
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* Pagination */}
        {totalPages > 1 && (
          <div className="flex items-center justify-between mt-4 pt-4 border-t border-vqc-border">
            <span className="text-vqc-muted text-sm">
              Page {page} of {totalPages}
            </span>
            <div className="flex gap-2">
              <button
                onClick={() => setPage(p => Math.max(1, p - 1))}
                disabled={page === 1}
                className="btn-secondary p-2"
              >
                <ChevronLeft className="w-4 h-4" />
              </button>
              <button
                onClick={() => setPage(p => Math.min(totalPages, p + 1))}
                disabled={page === totalPages}
                className="btn-secondary p-2"
              >
                <ChevronRight className="w-4 h-4" />
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
