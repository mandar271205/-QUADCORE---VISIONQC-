import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { ScanLine, XCircle, CheckCircle, AlertTriangle, Clock, ChevronRight } from 'lucide-react';
import { getTodayAnalytics } from '../api/analytics';
import { getInspections } from '../api/inspections';
import type { TodayAnalytics, InspectionListItem } from '../types';
import { DecisionBadge } from '../components/common/DecisionBadge';
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell, PieChart, Pie, Legend
} from 'recharts';

const COLORS = { PASS: '#22c55e', FAIL: '#ef4444', REVIEW: '#f59e0b' };

export const DashboardPage: React.FC = () => {
  const [analytics, setAnalytics] = useState<TodayAnalytics | null>(null);
  const [recent, setRecent] = useState<InspectionListItem[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const load = async () => {
      try {
        const [a, r] = await Promise.all([
          getTodayAnalytics(),
          getInspections({ page: 1, page_size: 10 }),
        ]);
        setAnalytics(a);
        setRecent(r.items);
      } catch (e) {
        console.error(e);
      } finally {
        setLoading(false);
      }
    };
    load();
  }, []);

  const pieData = analytics
    ? [
        { name: 'PASS', value: analytics.passed, fill: COLORS.PASS },
        { name: 'FAIL', value: analytics.failed, fill: COLORS.FAIL },
        { name: 'REVIEW', value: analytics.review, fill: COLORS.REVIEW },
      ]
    : [];

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="spinner w-8 h-8" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-vqc-text">Dashboard</h1>
          <p className="text-vqc-muted text-sm mt-1">Today's quality inspection overview</p>
        </div>
        <Link to="/inspect" className="btn-primary flex items-center gap-2">
          <ScanLine className="w-4 h-4" />
          Start Inspection
        </Link>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {[
          {
            icon: ScanLine, label: 'Total Inspections',
            value: analytics?.total ?? 0, color: 'text-vqc-accent',
          },
          {
            icon: XCircle, label: 'Rejected',
            value: analytics?.failed ?? 0, color: 'text-vqc-fail',
          },
          {
            icon: CheckCircle, label: 'Pass Rate',
            value: analytics
              ? analytics.total > 0
                ? `${((analytics.passed / analytics.total) * 100).toFixed(1)}%`
                : '—'
              : '—',
            color: 'text-vqc-pass',
          },
          {
            icon: Clock, label: 'Avg. Time',
            value: analytics
              ? `${Math.round(analytics.average_processing_time_ms)}ms`
              : '—',
            color: 'text-vqc-muted',
          },
        ].map(({ icon: Icon, label, value, color }) => (
          <div key={label} className="card">
            <div className="flex items-center gap-3 mb-3">
              <div className="w-9 h-9 bg-vqc-panel rounded-lg flex items-center justify-center">
                <Icon className={`w-4 h-4 ${color}`} />
              </div>
            </div>
            <div className={`text-2xl font-bold ${color}`}>{value}</div>
            <div className="text-vqc-muted text-xs mt-1">{label}</div>
          </div>
        ))}
      </div>

      {/* Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Donut chart */}
        <div className="card">
          <h3 className="section-title">Decision Distribution</h3>
          {analytics && analytics.total > 0 ? (
            <ResponsiveContainer width="100%" height={220}>
              <PieChart>
                <Pie
                  data={pieData}
                  dataKey="value"
                  nameKey="name"
                  cx="50%"
                  cy="50%"
                  innerRadius={55}
                  outerRadius={85}
                  paddingAngle={3}
                >
                  {pieData.map((entry, i) => (
                    <Cell key={i} fill={entry.fill} />
                  ))}
                </Pie>
                <Tooltip
                  contentStyle={{ background: '#1a1d27', border: '1px solid #2d3348', borderRadius: 8 }}
                  labelStyle={{ color: '#e2e8f0' }}
                />
                <Legend iconType="circle" iconSize={8} />
              </PieChart>
            </ResponsiveContainer>
          ) : (
            <div className="h-[220px] flex items-center justify-center text-vqc-muted text-sm">
              No inspections today
            </div>
          )}
        </div>

        {/* Summary stats */}
        <div className="card lg:col-span-2">
          <h3 className="section-title">Today's Summary</h3>
          <div className="space-y-4">
            {[
              { label: 'Rejection Rate', value: `${analytics?.rejection_rate ?? 0}%`, color: 'text-vqc-fail' },
              { label: 'Review Required', value: analytics?.review ?? 0, color: 'text-vqc-review' },
              { label: 'Avg. Anomaly Score', value: `${((analytics?.average_anomaly_score ?? 0) * 100).toFixed(1)}%`, color: 'text-vqc-text' },
              { label: 'Avg. Processing Time', value: `${Math.round(analytics?.average_processing_time_ms ?? 0)}ms`, color: 'text-vqc-text' },
            ].map(({ label, value, color }) => (
              <div key={label} className="flex items-center justify-between py-2 border-b border-vqc-border last:border-0">
                <span className="text-vqc-muted text-sm">{label}</span>
                <span className={`font-semibold text-sm ${color}`}>{value}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Recent inspections */}
      <div className="card">
        <div className="flex items-center justify-between mb-4">
          <h3 className="section-title mb-0">Recent Inspections</h3>
          <Link to="/history" className="text-vqc-accent text-sm hover:underline flex items-center gap-1">
            View all <ChevronRight className="w-3 h-3" />
          </Link>
        </div>
        {recent.length === 0 ? (
          <p className="text-vqc-muted text-sm text-center py-8">No inspections yet. Run your first inspection.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-vqc-border">
                  {['Time', 'Product', 'Decision', 'Score', 'Confidence', 'Duration'].map(h => (
                    <th key={h} className="text-left text-vqc-muted font-medium py-2 px-3 text-xs uppercase">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {recent.map((insp) => (
                  <tr
                    key={insp.inspection_id}
                    className="border-b border-vqc-border/50 hover:bg-vqc-panel/50 cursor-pointer transition-colors"
                    onClick={() => window.location.href = `/history/${insp.inspection_id}`}
                  >
                    <td className="py-3 px-3 text-vqc-muted font-mono text-xs">
                      {new Date(insp.created_at).toLocaleTimeString()}
                    </td>
                    <td className="py-3 px-3 text-vqc-text">
                      {insp.product?.name ?? <span className="text-vqc-muted">—</span>}
                    </td>
                    <td className="py-3 px-3">
                      <DecisionBadge decision={insp.decision} size="sm" />
                    </td>
                    <td className="py-3 px-3 text-vqc-text font-mono">
                      {insp.anomaly_score.toFixed(3)}
                    </td>
                    <td className="py-3 px-3 text-vqc-text font-mono">
                      {insp.confidence === 0 ? 'Unavailable' : `${(insp.confidence * 100).toFixed(1)}%`}
                    </td>
                    <td className="py-3 px-3 text-vqc-muted font-mono">
                      {insp.processing_time_ms}ms
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};
