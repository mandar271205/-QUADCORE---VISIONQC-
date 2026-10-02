import React from 'react';
import type { InspectionResponse } from '../../types';
import { DecisionBadge } from '../common/DecisionBadge';
import { AlertTriangle, Clock, Target, TrendingUp } from 'lucide-react';

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
      <div className="card text-center">
        <DecisionBadge decision={result.decision} size="lg" />
        {result.summary && (
          <p className="text-vqc-muted text-sm mt-3 leading-relaxed">{result.summary}</p>
        )}
      </div>

      {/* Scores */}
      <div className="grid grid-cols-2 gap-3">
        <div className="card-sm">
          <div className="flex items-center gap-2 mb-2">
            <TrendingUp className="w-4 h-4 text-vqc-accent" />
            <span className="label m-0">Anomaly Score</span>
          </div>
          <div className="stat-value text-xl">
            {(result.anomaly_score * 100).toFixed(1)}%
          </div>
          <div className="mt-2 bg-vqc-border rounded-full h-1.5">
            <div
              className={`h-1.5 rounded-full transition-all ${
                result.anomaly_score > result.threshold
                  ? 'bg-vqc-fail'
                  : 'bg-vqc-pass'
              }`}
              style={{ width: `${Math.min(result.anomaly_score * 100, 100)}%` }}
            />
          </div>
        </div>

        <div className="card-sm">
          <div className="flex items-center gap-2 mb-2">
            <Target className="w-4 h-4 text-vqc-accent" />
            <span className="label m-0">Confidence</span>
          </div>
          <div className="stat-value text-xl">
            {(result.confidence * 100).toFixed(1)}%
          </div>
          <div className="mt-2 bg-vqc-border rounded-full h-1.5">
            <div
              className="h-1.5 rounded-full bg-vqc-accent"
              style={{ width: `${result.confidence * 100}%` }}
            />
          </div>
        </div>

        <div className="card-sm">
          <span className="label">Threshold</span>
          <div className="stat-value text-xl text-vqc-muted">
            {(result.threshold * 100).toFixed(0)}%
          </div>
        </div>

        <div className="card-sm">
          <div className="flex items-center gap-2 mb-1">
            <Clock className="w-4 h-4 text-vqc-accent" />
            <span className="label m-0">Time</span>
          </div>
          <div className="stat-value text-xl">
            {result.processing_time_ms}ms
          </div>
        </div>
      </div>

      {/* Defects */}
      {result.defects.length > 0 && (
        <div className="card">
          <div className="flex items-center gap-2 mb-3">
            <AlertTriangle className="w-4 h-4 text-vqc-fail" />
            <h4 className="text-sm font-semibold text-vqc-text">
              Detected Deviations ({result.defects.length})
            </h4>
          </div>
          <div className="space-y-2">
            {result.defects.map((defect, i) => (
              <div key={i} className="bg-vqc-panel rounded-lg p-3">
                <div className="flex items-center justify-between mb-1">
                  <span className="text-sm font-medium text-vqc-text capitalize">
                    {defect.type.replace(/_/g, ' ')}
                  </span>
                  <span className={`text-xs font-semibold uppercase ${severityColor[defect.severity]}`}>
                    {defect.severity}
                  </span>
                </div>
                {defect.description && (
                  <p className="text-vqc-muted text-xs leading-relaxed">{defect.description}</p>
                )}
                {defect.region && (
                  <p className="text-vqc-muted text-xs mt-1 font-mono">
                    Location: ({(defect.region.x * 100).toFixed(0)}%,{' '}
                    {(defect.region.y * 100).toFixed(0)}%) —{' '}
                    {(defect.region.width * 100).toFixed(0)}×
                    {(defect.region.height * 100).toFixed(0)}%
                  </p>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Actions */}
      {onInspectNext && (
        <button onClick={onInspectNext} className="btn-primary w-full">
          Inspect Next Unit
        </button>
      )}
    </div>
  );
};
