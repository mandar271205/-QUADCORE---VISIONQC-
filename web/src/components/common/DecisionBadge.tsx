import React from 'react';
import type { Decision } from '../../types';
import { Badge } from '@/components/ui/badge';

interface Props {
  decision: Decision;
  size?: 'sm' | 'md' | 'lg';
}

const config = {
  PASS: {
    label: 'PASS',
    classes: 'bg-green-500/15 text-green-400 border-green-500/30 hover:bg-green-500/25 decision-pass',
    dotColor: 'bg-green-400',
  },
  FAIL: {
    label: 'FAIL',
    classes: 'bg-red-500/15 text-red-400 border-red-500/30 hover:bg-red-500/25 decision-fail',
    dotColor: 'bg-red-400',
  },
  REVIEW: {
    label: 'REVIEW',
    classes: 'bg-amber-500/15 text-amber-400 border-amber-500/30 hover:bg-amber-500/25',
    dotColor: 'bg-amber-400',
  },
  RETAKE: {
    label: 'RETAKE',
    classes: 'bg-slate-500/15 text-slate-400 border-slate-500/30 hover:bg-slate-500/25',
    dotColor: 'bg-slate-400',
  },
};

const sizeClasses = {
  sm: 'text-xs px-2.5 py-0.5',
  md: 'text-sm px-3 py-1',
  lg: 'text-lg px-5 py-2 font-bold tracking-wider',
};

export const DecisionBadge: React.FC<Props> = ({ decision, size = 'md' }) => {
  const { label, classes, dotColor } = config[decision];
  return (
    <Badge variant="outline" className={`inline-flex items-center gap-2 rounded-full font-semibold ${classes} ${sizeClasses[size]}`}>
      <span className={`w-2 h-2 rounded-full ${dotColor}`} />
      {label}
    </Badge>
  );
};
