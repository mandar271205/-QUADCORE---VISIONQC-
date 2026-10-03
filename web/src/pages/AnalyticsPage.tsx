import React, { useEffect, useState } from 'react';
import { getRangeAnalytics } from '../api/analytics';
import { getProducts } from '../api/products';
import type { AnalyticsResponse, Product } from '../types';
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
  LineChart, Line, CartesianGrid, Legend, PieChart, Pie, Cell,
} from 'recharts';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Input } from '@/components/ui/input';

const COLORS = { PASS: '#22c55e', FAIL: '#ef4444', REVIEW: '#f59e0b', RETAKE: '#64748b' };
const CHART_STYLE = {
  contentStyle: { background: '#1E293B', border: '1px solid #334155', borderRadius: 8, color: '#F8FAFC' },
  labelStyle: { color: '#F8FAFC' },
  itemStyle: { color: '#F8FAFC' },
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
    { name: 'RETAKE', value: data.total_retake, fill: COLORS.RETAKE },
  ].filter(d => d.value > 0) : [];

  return (
    <div className="space-y-6 max-w-[1600px] mx-auto">
      <div>
        <h1 className="text-3xl font-bold tracking-tight text-foreground">Analytics</h1>
        <p className="text-muted-foreground mt-1">Inspection performance trends and quality metrics</p>
      </div>

      {/* Filters */}
      <Card className="shadow-sm border-border bg-card">
        <CardContent className="p-4">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="space-y-1.5">
              <label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Product</label>
              <Select value={productFilter || 'all'} onValueChange={v => setProductFilter(v === 'all' ? '' : v)}>
                <SelectTrigger className="bg-secondary/30 h-10">
                  <SelectValue placeholder="All Products" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Products</SelectItem>
                  {products.map(p => (
                    <SelectItem key={p.id} value={p.id}>{p.name}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">From</label>
              <Input
                type="date"
                className="bg-secondary/30 h-10"
                value={dateFrom}
                onChange={e => setDateFrom(e.target.value)}
              />
            </div>
            <div className="space-y-1.5">
              <label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">To</label>
              <Input
                type="date"
                className="bg-secondary/30 h-10"
                value={dateTo}
                onChange={e => setDateTo(e.target.value)}
              />
            </div>
          </div>
        </CardContent>
      </Card>

      {loading ? (
        <div className="flex justify-center py-12"><div className="spinner w-8 h-8" /></div>
      ) : !data ? null : (
        <>
          {/* KPI tiles */}
          <div className="grid grid-cols-2 lg:grid-cols-6 gap-4">
            {[
              { label: 'Total Inspections', value: data.total_inspections, color: 'text-primary' },
              { label: 'Rejection Rate', value: `${data.overall_rejection_rate}%`, color: 'text-destructive' },
              { label: 'Review Rate', value: `${data.review_rate}%`, color: 'text-amber-500' },
              { label: 'Override Rate', value: `${data.override_rate}%`, color: 'text-purple-500' },
              { label: 'Avg. Anomaly Score', value: `${(data.average_anomaly_score * 100).toFixed(1)}%`, color: 'text-foreground' },
              { label: 'Image Retakes', value: data.total_retake, color: 'text-muted-foreground' },
            ].map(({ label, value, color }) => (
              <Card key={label} className="shadow-sm border-border bg-card">
                <CardContent className="p-6">
                  <div className={`text-2xl font-bold ${color}`}>{value}</div>
                  <div className="text-muted-foreground text-xs mt-1 font-semibold uppercase tracking-wider leading-tight">{label}</div>
                </CardContent>
              </Card>
            ))}
          </div>

          {/* Charts row */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* Stacked bar */}
            <Card className="shadow-sm border-border bg-card lg:col-span-2">
              <CardHeader><CardTitle className="text-base">Daily Inspections</CardTitle></CardHeader>
              <CardContent>
                {data.daily_stats.length === 0 ? (
                  <p className="text-muted-foreground text-sm text-center py-8">No data for selected range.</p>
                ) : (
                  <ResponsiveContainer width="100%" height={220}>
                    <BarChart data={data.daily_stats}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                      <XAxis dataKey="date" tick={{ fill: '#94A3B8', fontSize: 10 }} tickFormatter={v => v.slice(5)} />
                      <YAxis tick={{ fill: '#94A3B8', fontSize: 10 }} />
                      <Tooltip {...CHART_STYLE} />
                      <Legend iconType="circle" iconSize={8} />
                      <Bar dataKey="passed" stackId="a" fill={COLORS.PASS} name="PASS" radius={[0,0,0,0]} />
                      <Bar dataKey="review" stackId="a" fill={COLORS.REVIEW} name="REVIEW" />
                      <Bar dataKey="failed" stackId="a" fill={COLORS.FAIL} name="FAIL" radius={[4,4,0,0]} />
                    </BarChart>
                  </ResponsiveContainer>
                )}
              </CardContent>
            </Card>

            {/* Pie */}
            <Card className="shadow-sm border-border bg-card">
              <CardHeader><CardTitle className="text-base">Decision Split</CardTitle></CardHeader>
              <CardContent>
                {data.total_inspections === 0 ? (
                  <p className="text-muted-foreground text-sm text-center py-8">No data.</p>
                ) : (
                  <ResponsiveContainer width="100%" height={220}>
                    <PieChart>
                      <Pie data={pieData} dataKey="value" nameKey="name" cx="50%" cy="50%"
                        innerRadius={55} outerRadius={85} paddingAngle={3}>
                        {pieData.map((e, i) => <Cell key={i} fill={e.fill} stroke="rgba(0,0,0,0)" />)}
                      </Pie>
                      <Tooltip {...CHART_STYLE} />
                      <Legend iconType="circle" iconSize={8} />
                    </PieChart>
                  </ResponsiveContainer>
                )}
              </CardContent>
            </Card>
          </div>

          {/* Rejection rate trend */}
          <Card className="shadow-sm border-border bg-card">
            <CardHeader><CardTitle className="text-base">Rejection Rate Trend</CardTitle></CardHeader>
            <CardContent>
              {data.daily_stats.length === 0 ? (
                <p className="text-muted-foreground text-sm text-center py-8">No data.</p>
              ) : (
                <ResponsiveContainer width="100%" height={200}>
                  <LineChart data={data.daily_stats}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                    <XAxis dataKey="date" tick={{ fill: '#94A3B8', fontSize: 10 }} tickFormatter={v => v.slice(5)} />
                    <YAxis tick={{ fill: '#94A3B8', fontSize: 10 }} unit="%" />
                    <Tooltip {...CHART_STYLE} />
                    <Line type="monotone" dataKey="rejection_rate" stroke={COLORS.FAIL}
                      name="Rejection Rate %" dot={false} strokeWidth={2} />
                  </LineChart>
                </ResponsiveContainer>
              )}
            </CardContent>
          </Card>

          {/* By product table */}
          {data.product_distribution.length > 0 && (
            <Card className="shadow-sm border-border bg-card">
              <CardHeader><CardTitle className="text-base">By Product</CardTitle></CardHeader>
              <CardContent className="p-0">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-border">
                      {['Product', 'Total', 'Failed', 'Rejection Rate'].map(h => (
                        <th key={h} className="text-left text-muted-foreground font-semibold py-3 px-4 text-xs uppercase tracking-wider">{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {data.product_distribution.map((row, i) => (
                      <tr key={i} className="border-b border-border/50 hover:bg-secondary/30 transition-colors">
                        <td className="py-2.5 px-4 text-foreground font-medium">{row.product_name}</td>
                        <td className="py-2.5 px-4 text-foreground font-mono">{row.total}</td>
                        <td className="py-2.5 px-4 text-destructive font-mono">{row.failed}</td>
                        <td className="py-2.5 px-4 font-mono text-foreground">
                          {row.total > 0 ? `${((row.failed / row.total) * 100).toFixed(1)}%` : '—'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </CardContent>
            </Card>
          )}
        </>
      )}
    </div>
  );
};
