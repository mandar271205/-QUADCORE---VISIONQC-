import React from 'react';
import type { InspectionResponse } from '../../types';
import { DecisionBadge } from '../common/DecisionBadge';
import { AlertTriangle, Clock, Target, TrendingUp } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Progress } from '@/components/ui/progress';
import { Button } from '@/components/ui/button';

interface Props {
  result: InspectionResponse;
  onInspectNext?: () => void;
}

const severityColor = {
  low: 'text-yellow-400',
  medium: 'text-orange-400',
  high: 'text-red-400',
};

export const InspectionResultCard: React.FC<Props> = ({ result, onInspectNext }) => {
  return (
    <div className="space-y-4">
      {/* Decision */}
      <Card className="text-center shadow-md border-border bg-card">
        <CardContent className="pt-6 pb-6">
          <DecisionBadge decision={result.decision} size="lg" />
          {result.summary && (
            <p className="text-muted-foreground text-sm mt-4 leading-relaxed font-medium">{result.summary}</p>
          )}
        </CardContent>
      </Card>

      {/* Scores */}
      <div className="grid grid-cols-2 gap-4">
        {/* Anomaly Score */}
        <Card className="shadow-sm border-border bg-secondary/20">
          <CardContent className="p-4">
            <div className="flex items-center gap-2 mb-2">
              <TrendingUp className="w-4 h-4 text-primary" />
              <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground m-0">
                Anomaly Score
              </span>
            </div>

            <div className="text-2xl font-bold text-foreground mb-3">
              {result.anomaly_score.toFixed(3)}
            </div>

            <Progress
              value={Math.min(Math.max(result.anomaly_score * 100, 0), 100)}
              className="h-1.5 bg-border"
              indicatorClassName={
                result.anomaly_score > result.threshold
                  ? 'bg-destructive'
                  : 'bg-green-500'
              }
            />
          </CardContent>
        </Card>

        {/* Confidence */}
        <Card className="shadow-sm border-border bg-secondary/20">
          <CardContent className="p-4">
            <div className="flex items-center gap-2 mb-2">
              <Target className="w-4 h-4 text-primary" />
              <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground m-0">
                Confidence
              </span>
            </div>

            <div className="text-2xl font-bold text-foreground mb-3">
              {result.confidence === 0
                ? 'Unavailable'
                : `${(result.confidence * 100).toFixed(1)}%`}
            </div>

            <Progress
              value={
                result.confidence === 0
                  ? 0
                  : Math.min(Math.max(result.confidence * 100, 0), 100)
              }
              className="h-1.5 bg-border"
              indicatorClassName="bg-primary"
            />
          </CardContent>
        </Card>

        {/* Threshold */}
        <Card className="shadow-sm border-border bg-secondary/20">
          <CardContent className="p-4">
            <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground block mb-2">
              Threshold
            </span>

            <div className="text-2xl font-bold text-muted-foreground/70">
              {result.threshold.toFixed(3)}
            </div>
          </CardContent>
        </Card>

        {/* Processing Time */}
        <Card className="shadow-sm border-border bg-secondary/20">
          <CardContent className="p-4">
            <div className="flex items-center gap-2 mb-2">
              <Clock className="w-4 h-4 text-primary" />
              <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground m-0">
                Time
              </span>
            </div>

            <div className="text-2xl font-bold text-foreground">
              {result.processing_time_ms}ms
            </div>
          </CardContent>
        </Card>
      </div>

      <p className="text-muted-foreground text-xs leading-relaxed px-1">
        Anomaly scores use a 0–1 scale; they are not defect probabilities.
        REVIEW requests a manual check near the threshold.
      </p>

      {/* Defects */}
      {result.defects.length > 0 && (
        <Card className="border-destructive/30 shadow-md">
          <CardHeader className="pb-3 border-b border-border bg-destructive/5 rounded-t-lg">
            <CardTitle className="text-sm flex items-center gap-2 text-foreground font-semibold">
              <AlertTriangle className="w-4 h-4 text-destructive" />
              Detected Deviations ({result.defects.length})
            </CardTitle>
          </CardHeader>
          <CardContent className="p-4 space-y-3 bg-card">
            {result.defects.map((defect, i) => (
              <div key={i} className="bg-secondary/40 border border-border rounded-md p-3">
                <div className="flex items-center justify-between mb-1.5">
                  <span className="text-sm font-semibold text-foreground capitalize tracking-wide">
                    {defect.type.replace(/_/g, ' ')}
                  </span>
                  <span className={`text-xs font-bold uppercase tracking-widest ${severityColor[defect.severity]}`}>
                    {defect.severity}
                  </span>
                </div>
                {defect.description && (
                  <p className="text-muted-foreground text-sm leading-relaxed">{defect.description}</p>
                )}
                {defect.region && (
                  <p className="text-muted-foreground/70 text-xs mt-2 font-mono bg-background/50 inline-block px-2 py-1 rounded">
                    Loc: ({(defect.region.x * 100).toFixed(0)}%,{' '}
                    {(defect.region.y * 100).toFixed(0)}%) —{' '}
                    {(defect.region.width * 100).toFixed(0)}×
                    {(defect.region.height * 100).toFixed(0)}%
                  </p>
                )}
              </div>
            ))}
          </CardContent>
        </Card>
      )}

      {/* Actions */}
      {onInspectNext && (
        <Button onClick={onInspectNext} size="lg" className="w-full font-bold tracking-widest uppercase mt-4">
          Inspect Next Unit
        </Button>
      )}
    </div>
  );
};
