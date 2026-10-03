import React, { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { ScanLine, XCircle, CheckCircle, AlertTriangle, Clock, ChevronRight } from 'lucide-react';
import { getTodayAnalytics } from '../api/analytics';
import { getInspections } from '../api/inspections';
import type { TodayAnalytics, InspectionListItem } from '../types';
import { DecisionBadge } from '../components/common/DecisionBadge';
import {
  PieChart, Pie, Legend, Tooltip, ResponsiveContainer, Cell
} from 'recharts';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';

const COLORS = { PASS: '#22c55e', FAIL: '#ef4444', REVIEW: '#f59e0b' };

export const DashboardPage: React.FC = () => {
  const navigate = useNavigate();
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
        <div className="spinner w-8 h-8 border-primary/20 border-t-primary" />
      </div>
    );
  }

  return (
    <div className="space-y-6 max-w-[1600px] mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight text-foreground">Dashboard</h1>
          <p className="text-muted-foreground mt-1">Today's quality inspection overview</p>
        </div>
        <Link to="/inspect">
          <Button size="lg" className="font-semibold tracking-wide shadow-sm">
            <ScanLine className="w-4 h-4 mr-2" />
            Start Inspection
          </Button>
        </Link>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {[
          {
            icon: ScanLine, label: 'Total Inspections',
            value: analytics?.total ?? 0, color: 'text-primary',
          },
          {
            icon: XCircle, label: 'Rejected',
            value: analytics?.failed ?? 0, color: 'text-destructive',
          },
          {
            icon: CheckCircle, label: 'Pass Rate',
            value: analytics
              ? analytics.total > 0
                ? `${((analytics.passed / analytics.total) * 100).toFixed(1)}%`
                : '—'
              : '—',
            color: 'text-green-500',
          },
          {
            icon: Clock, label: 'Avg. Time',
            value: analytics
              ? `${Math.round(analytics.average_processing_time_ms)}ms`
              : '—',
            color: 'text-muted-foreground',
          },
        ].map(({ icon: Icon, label, value, color }) => (
          <Card key={label} className="shadow-sm border-border bg-card">
            <CardContent className="p-6">
              <div className="flex items-center gap-3 mb-4">
                <div className="w-10 h-10 bg-secondary/80 rounded-lg flex items-center justify-center border border-border">
                  <Icon className={`w-5 h-5 ${color}`} />
                </div>
              </div>
              <div className={`text-3xl font-bold ${color}`}>{value}</div>
              <div className="text-muted-foreground text-xs font-semibold uppercase tracking-wider mt-1">{label}</div>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Donut chart */}
        <Card className="shadow-sm border-border bg-card">
          <CardHeader>
            <CardTitle className="text-lg">Decision Distribution</CardTitle>
          </CardHeader>
          <CardContent>
            {analytics && analytics.total > 0 ? (
              <ResponsiveContainer width="100%" height={240}>
                <PieChart>
                  <Pie
                    data={pieData}
                    dataKey="value"
                    nameKey="name"
                    cx="50%"
                    cy="50%"
                    innerRadius={65}
                    outerRadius={95}
                    paddingAngle={3}
                  >
                    {pieData.map((entry, i) => (
                      <Cell key={i} fill={entry.fill} stroke="rgba(0,0,0,0)" />
                    ))}
                  </Pie>
                  <Tooltip
                    contentStyle={{ background: '#0F172A', border: '1px solid #334155', borderRadius: 8, color: '#F8FAFC' }}
                    itemStyle={{ color: '#F8FAFC' }}
                  />
                  <Legend iconType="circle" iconSize={8} />
                </PieChart>
              </ResponsiveContainer>
            ) : (
              <div className="h-[240px] flex items-center justify-center text-muted-foreground text-sm font-medium">
                No inspections today
              </div>
            )}
          </CardContent>
        </Card>

        {/* Summary stats */}
        <Card className="shadow-sm border-border bg-card lg:col-span-2">
          <CardHeader>
            <CardTitle className="text-lg">Today's Summary</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-1">
              {[
                { label: 'Rejection Rate', value: `${analytics?.rejection_rate ?? 0}%`, color: 'text-destructive' },
                { label: 'Review Required', value: analytics?.review ?? 0, color: 'text-amber-500' },
                { label: 'Avg. Anomaly Score', value: `${((analytics?.average_anomaly_score ?? 0) * 100).toFixed(1)}%`, color: 'text-foreground' },
                { label: 'Avg. Processing Time', value: `${Math.round(analytics?.average_processing_time_ms ?? 0)}ms`, color: 'text-foreground' },
              ].map(({ label, value, color }) => (
                <div key={label} className="flex items-center justify-between py-3 px-2 border-b border-border/50 hover:bg-secondary/30 rounded-md transition-colors last:border-0">
                  <span className="text-muted-foreground font-medium text-sm">{label}</span>
                  <span className={`font-bold ${color}`}>{value}</span>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Recent inspections */}
      <Card className="shadow-sm border-border bg-card">
        <CardHeader className="flex flex-row items-center justify-between">
          <div>
            <CardTitle className="text-lg">Recent Inspections</CardTitle>
            <CardDescription>Latest units processed through the system</CardDescription>
          </div>
          <Link to="/history">
            <Button variant="ghost" size="sm" className="text-primary hover:text-primary/90">
              View all <ChevronRight className="w-4 h-4 ml-1" />
            </Button>
          </Link>
        </CardHeader>
        <CardContent className="p-0">
          {recent.length === 0 ? (
            <p className="text-muted-foreground text-sm text-center py-8">No inspections yet. Run your first inspection.</p>
          ) : (
            <Table>
              <TableHeader className="bg-secondary/30">
                <TableRow className="border-border">
                  {['Time', 'Product', 'Decision', 'Score', 'Confidence', 'Duration'].map(h => (
                    <TableHead key={h} className="text-muted-foreground font-semibold text-xs uppercase tracking-wider">{h}</TableHead>
                  ))}
                </TableRow>
              </TableHeader>
              <TableBody>
                {recent.map((insp) => (
                  <TableRow
                    key={insp.inspection_id}
                    className="border-border/50 hover:bg-secondary/40 cursor-pointer transition-colors"
                    onClick={() => navigate(`/history/${insp.inspection_id}`)}
                  >
                    <TableCell className="text-muted-foreground font-mono text-xs">
                      {new Date(insp.created_at).toLocaleTimeString()}
                    </TableCell>
                    <TableCell className="font-medium text-foreground">
                      {insp.product?.name ?? <span className="text-muted-foreground/50">—</span>}
                    </TableCell>
                    <TableCell>
                      <DecisionBadge decision={insp.decision} size="sm" />
                    </TableCell>
                    <TableCell className="text-foreground font-mono font-medium">
                      {insp.anomaly_score.toFixed(3)}
                    </TableCell>
                    <TableCell className="text-foreground font-mono font-medium">
                      {insp.confidence === 0
                        ? 'Unavailable'
                        : `${(insp.confidence * 100).toFixed(1)}%`}
                    </TableCell>
                    <TableCell className="text-muted-foreground font-mono text-xs">
                      {insp.processing_time_ms}ms
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  );
};
