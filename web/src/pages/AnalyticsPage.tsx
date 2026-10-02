import React, { useEffect, useState } from 'react';
import { getRangeAnalytics } from '../api/analytics';
import { getProducts } from '../api/products';
import type { AnalyticsResponse, Product } from '../types';
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
  LineChart, Line, CartesianGrid, Legend, PieChart, Pie, Cell
} from 'recharts';

const COLORS = { PASS: '#22c55e', FAIL: '#ef4444', REVIEW: '#f59e0b' };
const CHART_STYLE = {
  contentStyle: { background: '#1a1d27', border: '1px solid #2d3348', borderRadius: 8 },
  labelStyle: { color: '#e2e8f0' },
};

export const AnalyticsPage: React.FC = () => {
  const [data, setData] = useState<AnalyticsResponse | null>(null);
  const [products, setProducts] = useState<Product[]>([]);
  const [loading, setLoading] = useState(true);
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [productFilter, setProductFilter] = useState('');

  const load = async () => {
    setLoading(true);
    try {
      const [a, p] = await Promise.all([
        getRangeAnalytics({
          date_from: dateFrom || undefined,
          date_to: dateTo || undefined,
          product_id: productFilter || undefined,
        }),
        getProducts(),
      ]);
      setData(a);
      setProducts(p);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, [dateFrom, dateTo, productFilter]);

  const pieData = data ? [
    { name: 'PASS', value: data.total_passed, fill: COLORS.PASS },
    { name: 'FAIL', value: data.total_failed, fill: COLORS.FAIL },
    { name: 'REVIEW', value: data.total_review, fill: COLORS.REVIEW },
  ] : [];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-vqc-text">Analytics</h1>
        <p className="text-vqc-muted text-sm mt-1">Inspection performance trends and quality metrics</p>
      </div>

      {/* Filters */}
      <div className="card">
        <div className="grid grid-cols-3 gap-4">
          <div>
            <label className="label">Product</label>
            <select className="input" value={productFilter}
              onChange={e => setProductFilter(e.target.value)}>
              <option value="">All Products</option>
              {products.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select>
          </div>
          <div>
            <label className="label">From</label>
            <input type="date" className="input" value={dateFrom}
              onChange={e => setDateFrom(e.target.value)} />
          </div>
          <div>
            <label className="label">To</label>
            <input type="date" className="input" value={dateTo}
              onChange={e => setDateTo(e.target.value)} />
          </div>
        </div>
      </div>

      {loading ? (
        <div className="flex justify-center py-12"><div className="spinner w-8 h-8" /></div>
      ) : !data ? null : (
        <>
          {/* KPI tiles */}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            {[
              { label: 'Total Inspections', value: data.total_inspections, color: 'text-vqc-accent' },
              { label: 'Rejection Rate', value: `${data.overall_rejection_rate}%`, color: 'text-vqc-fail' },
              { label: 'Avg. Anomaly Score', value: `${(data.average_anomaly_score * 100).toFixed(1)}%`, color: 'text-vqc-text' },
              { label: 'Avg. Processing Time', value: `${Math.round(data.average_processing_time_ms)}ms`, color: 'text-vqc-muted' },
            ].map(({ label, value, color }) => (
              <div key={label} className="card">
                <div className={`text-2xl font-bold ${color}`}>{value}</div>
                <div className="text-vqc-muted text-xs mt-1">{label}</div>
              </div>
            ))}
          </div>

          {/* Charts row */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* Stacked bar: daily inspections */}
            <div className="card lg:col-span-2">
              <h3 className="section-title">Daily Inspections</h3>
              {data.daily_stats.length === 0 ? (
                <p className="text-vqc-muted text-sm text-center py-8">No data for selected range.</p>
              ) : (
                <ResponsiveContainer width="100%" height={220}>
                  <BarChart data={data.daily_stats}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#2d3348" />
                    <XAxis dataKey="date" tick={{ fill: '#8b92a5', fontSize: 10 }} tickFormatter={v => v.slice(5)} />
                    <YAxis tick={{ fill: '#8b92a5', fontSize: 10 }} />
                    <Tooltip {...CHART_STYLE} />
                    <Legend iconType="circle" iconSize={8} />
                    <Bar dataKey="passed" stackId="a" fill={COLORS.PASS} name="PASS" radius={[0,0,0,0]} />
                    <Bar dataKey="review" stackId="a" fill={COLORS.REVIEW} name="REVIEW" />
                    <Bar dataKey="failed" stackId="a" fill={COLORS.FAIL} name="FAIL" radius={[4,4,0,0]} />
                  </BarChart>
                </ResponsiveContainer>
              )}
            </div>

            {/* Pie */}
            <div className="card">
              <h3 className="section-title">Decision Split</h3>
              {data.total_inspections === 0 ? (
                <p className="text-vqc-muted text-sm text-center py-8">No data.</p>
              ) : (
                <ResponsiveContainer width="100%" height={220}>
                  <PieChart>
                    <Pie data={pieData} dataKey="value" nameKey="name" cx="50%" cy="50%"
                      innerRadius={55} outerRadius={85} paddingAngle={3}>
                      {pieData.map((e, i) => <Cell key={i} fill={e.fill} />)}
                    </Pie>
                    <Tooltip {...CHART_STYLE} />
                    <Legend iconType="circle" iconSize={8} />
                  </PieChart>
                </ResponsiveContainer>
              )}
            </div>
          </div>

          {/* Rejection rate trend */}
          <div className="card">
            <h3 className="section-title">Rejection Rate Trend</h3>
            {data.daily_stats.length === 0 ? (
              <p className="text-vqc-muted text-sm text-center py-8">No data.</p>
            ) : (
              <ResponsiveContainer width="100%" height={200}>
                <LineChart data={data.daily_stats}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#2d3348" />
                  <XAxis dataKey="date" tick={{ fill: '#8b92a5', fontSize: 10 }} tickFormatter={v => v.slice(5)} />
                  <YAxis tick={{ fill: '#8b92a5', fontSize: 10 }} unit="%" />
                  <Tooltip {...CHART_STYLE} />
                  <Line type="monotone" dataKey="rejection_rate" stroke={COLORS.FAIL}
                    name="Rejection Rate %" dot={false} strokeWidth={2} />
                </LineChart>
              </ResponsiveContainer>
            )}
          </div>

          {/* Product distribution table */}
          {data.product_distribution.length > 0 && (
            <div className="card">
              <h3 className="section-title">By Product</h3>
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-vqc-border">
                    {['Product', 'Total', 'Failed', 'Rejection Rate'].map(h => (
                      <th key={h} className="text-left text-vqc-muted font-medium py-2 px-3 text-xs uppercase">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {data.product_distribution.map((row, i) => (
                    <tr key={i} className="border-b border-vqc-border/50">
                      <td className="py-2.5 px-3 text-vqc-text">{row.product_name}</td>
                      <td className="py-2.5 px-3 text-vqc-text font-mono">{row.total}</td>
                      <td className="py-2.5 px-3 text-vqc-fail font-mono">{row.failed}</td>
                      <td className="py-2.5 px-3 font-mono text-vqc-text">
                        {row.total > 0 ? `${((row.failed / row.total) * 100).toFixed(1)}%` : '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </div>
  );
};
