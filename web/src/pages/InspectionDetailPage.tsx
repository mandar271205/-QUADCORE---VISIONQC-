import React, { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { ArrowLeft, Trash2 } from 'lucide-react';
import { getInspection, deleteInspection } from '../api/inspections';
import type { InspectionResponse } from '../types';
import { AnomalyHeatmapViewer } from '../components/inspection/AnomalyHeatmapViewer';
import { InspectionResultCard } from '../components/inspection/InspectionResultCard';

export const InspectionDetailPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [inspection, setInspection] = useState<InspectionResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [deleting, setDeleting] = useState(false);

  useEffect(() => {
    if (!id) return;
    getInspection(id)
      .then(setInspection)
      .catch(() => setInspection(null))
      .finally(() => setLoading(false));
  }, [id]);

  const handleDelete = async () => {
    if (!id || !confirm('Delete this inspection record?')) return;
    setDeleting(true);
    try {
      await deleteInspection(id);
      navigate('/history');
    } finally {
      setDeleting(false);
    }
  };

  if (loading) return <div className="flex justify-center py-16"><div className="spinner w-8 h-8" /></div>;
  if (!inspection) return <div className="text-vqc-muted">Inspection not found.</div>;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <button onClick={() => navigate('/history')} className="btn-secondary p-2">
            <ArrowLeft className="w-4 h-4" />
          </button>
          <div>
            <h1 className="text-2xl font-bold text-vqc-text">
              {inspection.product?.name ?? 'Unknown Product'}
            </h1>
            <p className="text-vqc-muted text-xs font-mono mt-0.5">
              {inspection.inspection_id}
            </p>
          </div>
        </div>
        <button onClick={handleDelete} disabled={deleting} className="btn-danger flex items-center gap-2">
          <Trash2 className="w-4 h-4" />
          {deleting ? 'Deleting...' : 'Delete'}
        </button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
        <div className="lg:col-span-3">
          <AnomalyHeatmapViewer
            originalUrl={inspection.original_image_url}
            heatmapUrl={inspection.heatmap_url}
          />
        </div>
        <div className="lg:col-span-2">
          <InspectionResultCard result={inspection} />
        </div>
      </div>
    </div>
  );
};
