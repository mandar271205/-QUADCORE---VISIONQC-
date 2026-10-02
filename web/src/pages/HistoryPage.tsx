import React, { useEffect, useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { Search, Filter, ChevronLeft, ChevronRight } from 'lucide-react';
import { getInspections } from '../api/inspections';
import { getProducts } from '../api/products';
import type { InspectionListItem, Product } from '../types';
import { DecisionBadge } from '../components/common/DecisionBadge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';

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
        ...(filters.product_id && filters.product_id !== 'all' ? { product_id: filters.product_id } : {}),
        ...(filters.decision && filters.decision !== 'all' ? { decision: filters.decision } : {}),
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
    <div className="space-y-6 max-w-[1600px] mx-auto">
      <div>
        <h1 className="text-3xl font-bold tracking-tight text-foreground">Inspection History</h1>
        <p className="text-muted-foreground mt-1">Search and filter {total} past inspections</p>
      </div>

      {/* Filters */}
      <Card className="shadow-sm border-border bg-card">
        <CardContent className="p-4">
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            <div className="space-y-1.5">
              <label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Product</label>
              <Select value={filters.product_id || 'all'} onValueChange={(v: string) => handleFilterChange('product_id', v)}>
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
              <label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Decision</label>
              <Select value={filters.decision || 'all'} onValueChange={(v: string) => handleFilterChange('decision', v)}>
                <SelectTrigger className="bg-secondary/30 h-10">
                  <SelectValue placeholder="All Decisions" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All</SelectItem>
                  <SelectItem value="PASS">PASS</SelectItem>
                  <SelectItem value="FAIL">FAIL</SelectItem>
                  <SelectItem value="REVIEW">REVIEW</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">From Date</label>
              <Input 
                type="date" 
                value={filters.date_from}
                onChange={e => handleFilterChange('date_from', e.target.value)} 
                className="bg-secondary/30 h-10"
              />
            </div>
            <div className="space-y-1.5">
              <label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">To Date</label>
              <Input 
                type="date" 
                value={filters.date_to}
                onChange={e => handleFilterChange('date_to', e.target.value)} 
                className="bg-secondary/30 h-10"
              />
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Table */}
      <Card className="shadow-sm border-border bg-card">
        <CardContent className="p-0">
          {loading ? (
            <div className="flex justify-center py-16">
              <div className="spinner w-8 h-8 border-primary/20 border-t-primary" />
            </div>
          ) : items.length === 0 ? (
            <div className="text-center py-16">
              <Filter className="w-10 h-10 mx-auto text-muted-foreground/30 mb-3" />
              <p className="text-muted-foreground text-sm font-medium">No inspections found matching filters.</p>
            </div>
          ) : (
            <Table>
              <TableHeader className="bg-secondary/30">
                <TableRow className="border-border">
                  {['Timestamp', 'Product', 'Decision', 'Anomaly Score', 'Confidence', 'Time (ms)'].map(h => (
                    <TableHead key={h} className="text-muted-foreground font-semibold text-xs uppercase tracking-wider h-11">{h}</TableHead>
                  ))}
                </TableRow>
              </TableHeader>
              <TableBody>
                {items.map(insp => (
                  <TableRow
                    key={insp.inspection_id}
                    className="border-border/50 hover:bg-secondary/40 cursor-pointer transition-colors"
                    onClick={() => navigate(`/history/${insp.inspection_id}`)}
                  >
                    <TableCell className="text-muted-foreground font-mono text-xs">
                      {new Date(insp.created_at).toLocaleString()}
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
        
        {/* Pagination */}
        {totalPages > 1 && (
          <div className="flex items-center justify-between p-4 border-t border-border bg-secondary/10 rounded-b-xl">
            <span className="text-muted-foreground text-sm font-medium">
              Page {page} of {totalPages}
            </span>
            <div className="flex gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => setPage(p => Math.max(1, p - 1))}
                disabled={page === 1}
              >
                <ChevronLeft className="w-4 h-4 mr-1" /> Prev
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={() => setPage(p => Math.min(totalPages, p + 1))}
                disabled={page === totalPages}
              >
                Next <ChevronRight className="w-4 h-4 ml-1" />
              </Button>
            </div>
          </div>
        )}
      </Card>
    </div>
  );
};
