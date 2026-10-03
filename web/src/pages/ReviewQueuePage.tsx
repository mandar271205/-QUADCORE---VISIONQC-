import React, { useEffect, useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { CheckCircle, XCircle, AlertTriangle, UserCheck, MessageSquare, ExternalLink } from 'lucide-react';
import { format } from 'date-fns';
import { reviewsApi } from '../api/reviews';
import { Link } from 'react-router-dom';
import type { PendingReviewItem } from '../types';

export const ReviewQueuePage: React.FC = () => {
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState('pending');
  const queryClient = useQueryClient();

  const { data, isLoading } = useQuery({
    queryKey: ['reviews', page, status],
    queryFn: () => reviewsApi.getPendingReviews(page, 20, status),
    refetchInterval: 10000,
  });

  const submitDecision = useMutation({
    mutationFn: ({ inspectionId, action, note }: { inspectionId: string, action: 'accept' | 'reject', note?: string }) =>
      reviewsApi.submitReviewDecision(inspectionId, action, note),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['reviews'] });
    },
  });

  if (isLoading) {
    return <div className="p-8 text-center text-muted-foreground">Loading queue...</div>;
  }

  const items = data?.items || [];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Review Queue</h1>
          <p className="text-muted-foreground mt-2">
            Human-in-the-loop review for ambiguous inspections.
          </p>
        </div>
        <div className="flex bg-secondary p-1 rounded-md">
          {['pending', 'accepted', 'rejected'].map(tab => (
            <button
              key={tab}
              onClick={() => { setStatus(tab); setPage(1); }}
              className={`px-4 py-1.5 text-sm font-medium rounded-sm capitalize transition-colors ${
                status === tab 
                  ? 'bg-background text-foreground shadow' 
                  : 'text-muted-foreground hover:text-foreground'
              }`}
            >
              {tab}
            </button>
          ))}
        </div>
      </div>

      {items.length === 0 ? (
        <div className="flex flex-col items-center justify-center p-12 bg-card border border-border rounded-lg text-center">
          <UserCheck className="w-12 h-12 text-muted-foreground mb-4 opacity-50" />
          <h3 className="text-lg font-medium text-foreground">Queue is empty</h3>
          <p className="text-muted-foreground mt-1">No inspections currently require human review.</p>
        </div>
      ) : (
        <div className="grid gap-6">
          {items.map(item => (
            <ReviewCard 
              key={item.review_id} 
              item={item} 
              onDecision={(action, note) => submitDecision.mutate({ inspectionId: item.inspection_id, action, note })}
              isSubmitting={submitDecision.isPending}
            />
          ))}
        </div>
      )}
    </div>
  );
};

const ReviewCard: React.FC<{
  item: PendingReviewItem;
  onDecision: (action: 'accept' | 'reject', note?: string) => void;
  isSubmitting: boolean;
}> = ({ item, onDecision, isSubmitting }) => {
  const [note, setNote] = useState('');

  return (
    <div className="bg-card border border-border rounded-lg overflow-hidden flex flex-col md:flex-row">
      {/* Image Section */}
      <div className="w-full md:w-[400px] flex-shrink-0 bg-black/90 p-4 relative min-h-[300px]">
        {item.original_image_url ? (
          <img 
            src={item.original_image_url} 
            alt="Product" 
            className="w-full h-full object-contain"
          />
        ) : (
          <div className="w-full h-full flex items-center justify-center text-muted-foreground">
            No image available
          </div>
        )}
        {item.heatmap_url && (
          <img 
            src={item.heatmap_url} 
            alt="Anomaly Heatmap" 
            className="absolute inset-0 w-full h-full object-contain opacity-60 mix-blend-screen pointer-events-none"
          />
        )}
      </div>

      {/* Details Section */}
      <div className="flex-1 p-6 flex flex-col">
        <div className="flex items-start justify-between mb-4">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <span className="text-xs font-semibold px-2 py-0.5 rounded-full bg-amber-500/10 text-amber-500 uppercase tracking-wider">
                REVIEW REQUESTED
              </span>
              <span className="text-xs text-muted-foreground">
                {format(new Date(item.queued_at), 'MMM d, h:mm a')}
              </span>
            </div>
            <h3 className="text-xl font-bold">{item.product?.name || 'Unknown Product'}</h3>
            <div className="flex items-center gap-4 mt-2 text-sm">
              <div>
                <span className="text-muted-foreground">Severity: </span>
                <span className={`font-medium ${
                  item.operational_severity === 'CRITICAL' ? 'text-red-500' :
                  item.operational_severity === 'MODERATE' ? 'text-amber-500' : 'text-foreground'
                }`}>{item.operational_severity}</span>
              </div>
              <div>
                <span className="text-muted-foreground">AI Score: </span>
                <span className="font-medium text-amber-500">
                  {(item.anomaly_score * 100).toFixed(1)}%
                </span>
                <span className="text-xs text-muted-foreground ml-1">
                  (Threshold: {(item.threshold * 100).toFixed(1)}%)
                </span>
              </div>
            </div>
          </div>
          
          <Link 
            to={`/history/${item.inspection_id}`}
            className="text-primary hover:bg-primary/10 p-2 rounded-md transition-colors"
            title="View Full Inspection"
          >
            <ExternalLink className="w-5 h-5" />
          </Link>
        </div>

        {/* AI Findings */}
        <div className="bg-secondary/50 rounded-md p-4 mb-6 flex-1">
          <h4 className="text-sm font-semibold flex items-center gap-2 mb-2">
            <AlertTriangle className="w-4 h-4 text-amber-500" />
            AI Findings
          </h4>
          {item.conformity_summary && (
            <p className="text-sm text-muted-foreground mb-3">{item.conformity_summary}</p>
          )}
          {item.defects.length > 0 ? (
            <ul className="space-y-2">
              {item.defects.map((d, i) => (
                <li key={i} className="text-sm flex gap-2">
                  <span className="w-2 h-2 mt-1.5 rounded-full bg-amber-500 flex-shrink-0" />
                  <div>
                    <span className="font-medium">{d.type}</span>
                    {d.description && <span className="text-muted-foreground ml-2">— {d.description}</span>}
                  </div>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-muted-foreground italic">AI detected high anomaly score but no specific bounding boxes.</p>
          )}
        </div>

        {/* Action Section */}
        {item.review_status === 'pending' ? (
          <div className="mt-auto space-y-4">
            <div className="flex items-center gap-2">
              <MessageSquare className="w-4 h-4 text-muted-foreground" />
              <input 
                type="text" 
                placeholder="Add optional supervisor note..."
                value={note}
                onChange={e => setNote(e.target.value)}
                className="flex-1 bg-background border border-input rounded-md px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-primary"
              />
            </div>
            <div className="flex gap-3">
              <button
                onClick={() => onDecision('accept', note)}
                disabled={isSubmitting}
                className="flex-1 flex items-center justify-center gap-2 bg-green-500/10 text-green-500 hover:bg-green-500/20 px-4 py-2.5 rounded-md font-medium transition-colors"
              >
                <CheckCircle className="w-5 h-5" />
                ACCEPT (PASS)
              </button>
              <button
                onClick={() => onDecision('reject', note)}
                disabled={isSubmitting}
                className="flex-1 flex items-center justify-center gap-2 bg-red-500/10 text-red-500 hover:bg-red-500/20 px-4 py-2.5 rounded-md font-medium transition-colors"
              >
                <XCircle className="w-5 h-5" />
                REJECT (FAIL)
              </button>
            </div>
          </div>
        ) : (
          <div className="mt-auto p-4 bg-background border border-border rounded-md">
            <div className="flex items-center gap-2 mb-1">
              <UserCheck className="w-4 h-4 text-primary" />
              <span className="font-medium">Reviewed on {format(new Date(item.reviewed_at || ''), 'MMM d, h:mm a')}</span>
            </div>
            <div className="text-sm">
              Decision: <strong className={item.human_decision === 'PASS' ? 'text-green-500' : 'text-red-500'}>{item.human_decision}</strong>
            </div>
            {item.note && (
              <div className="text-sm text-muted-foreground mt-2 italic">"{item.note}"</div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};
