import React, { useEffect, useState } from 'react';
import apiClient from '../api/client';

type MetricRow = {
  category: string; model: string; f2: number | null; f1: number | null;
  precision: number | null; recall: number | null; accuracy: number | null;
  image_auroc: number | null; pixel_auroc: number | null;
  false_accept_rate: number | null; false_reject_rate: number | null; latency_ms: number | null;
  examples: { label: string; filename: string; url: string }[];
};
type Comparison = { state: string; shots: number; protocol?: string; results: MetricRow[] };
const columns = ['f2', 'recall', 'precision', 'f1', 'accuracy', 'image_auroc', 'pixel_auroc', 'false_accept_rate', 'false_reject_rate', 'latency_ms'] as const;
const titles = ['F2', 'Recall', 'Precision', 'F1', 'Accuracy', 'Image AUROC', 'Pixel AUROC', 'FAR', 'FRR', 'ms/image'];

export const ComparisonPage: React.FC = () => {
  const [data, setData] = useState<Comparison | null>(null);
  const [error, setError] = useState('');
  const [category, setCategory] = useState('screw');
  useEffect(() => {
    apiClient.get<Comparison>('/experiments/comparison').then(response => setData(response.data)).catch(error => setError(error.message));
  }, []);
  const rows = data?.results.filter(row => row.category === category) || [];
  return <div className="space-y-6">
    <div><h1 className="text-2xl font-bold text-vqc-text">Model Comparison</h1>
      <p className="text-vqc-muted text-sm mt-1">Real {data?.shots || 30}-shot baseline results. F2 emphasizes defect recall.</p></div>
    {error && <p role="alert" className="text-red-300">{error}</p>}
    {!data && !error && <p className="text-vqc-muted">Loading experiment results...</p>}
    {data && <>
      <div className="card space-y-3"><p className="text-vqc-muted text-sm">{data.protocol || 'Experiments are pending. Metrics will appear after evaluation.'}</p>
        <select aria-label="Comparison category" className="input" value={category} onChange={event => setCategory(event.target.value)}>
          {['screw', 'cable', 'transistor'].map(value => <option key={value} value={value}>{value}</option>)}
        </select>
        <p className="text-vqc-muted text-xs">FAR: missed defects / all defects. FRR: rejected normals / all normals. Missing metrics are unavailable.</p>
      </div>
      <div className="card overflow-x-auto"><table className="w-full text-sm"><thead><tr className="border-b border-vqc-border">
        {['Model', ...titles].map(title => <th key={title} className="text-left text-vqc-muted p-2 whitespace-nowrap">{title}</th>)}
      </tr></thead><tbody>{rows.map(row => <tr key={row.model} className="border-b border-vqc-border/50"><td className="p-2 capitalize">{row.model}</td>
        {columns.map(key => <td key={key} className="p-2 font-mono whitespace-nowrap">{row[key] == null ? 'Unavailable' : `${(row[key]! * (key === 'latency_ms' ? 1 : 100)).toFixed(2)}${key === 'latency_ms' ? '' : '%'}`}</td>)}
      </tr>)}</tbody></table></div>
      {rows.filter(row => row.false_reject_rate === 1).map(row => <p key={row.model} className="text-vqc-review text-sm">{row.model}: this baseline rejected every normal image in the held-out split. Its F2 score should be read alongside the false reject rate.</p>)}
      {rows.map(row => <div key={row.model} className="card"><h2 className="section-title capitalize">{row.model} example overlays</h2>
        <p className="text-vqc-muted text-xs mb-3">Five GOOD and five DEFECT images selected with a fixed seed. Colors indicate anomaly intensity.</p>
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3">{row.examples.map(example => <figure key={example.url}>
          <img className="w-full aspect-square object-contain rounded-lg bg-vqc-panel" src={example.url} alt={`${row.model} ${example.label} ${example.filename}`} />
          <figcaption className="text-vqc-muted text-xs mt-1">{example.label} · {example.filename}</figcaption>
        </figure>)}</div>
      </div>)}
    </>}
  </div>;
};
