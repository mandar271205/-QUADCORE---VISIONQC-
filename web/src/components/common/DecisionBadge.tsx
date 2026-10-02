import React from 'react';
import type { Decision } from '../../types';

interface Props {
  decision: Decision;
  size?: 'sm' | 'md' | 'lg';
}

const config = {
  PASS: {
    label: 'PASS',
    classes: 'bg-green-500/15 text-green-400 border-green-500/30 decision-pass',
    dotColor: 'bg-green-400',
  },
  FAIL: {
    label: 'FAIL',
    classes: 'bg-red-500/15 text-red-400 border-red-500/30 decision-fail',
    dotColor: 'bg-red-400',
  },
  REVIEW: {
    label: 'REVIEW',
    classes: 'bg-amber-500/15 text-amber-400 border-amber-500/30',
    dotColor: 'bg-amber-400',
  },
};

const sizeClasses = {
  sm: 'text-xs px-2.5 py-1',
  md: 'text-sm px-3 py-1.5',
  lg: 'text-lg px-5 py-2.5 font-bold tracking-wider',
};

export const DecisionBadge: React.FC<Props> = ({ decision, size = 'md' }) => {
  const { label, classes, dotColor } = config[decision];
  return (
    <span className={`inline-flex items-center gap-2 rounded-full border font-semibold ${classes} ${sizeClasses[size]}`}>
      <span className={`w-2 h-2 rounded-full ${dotColor}`} />
      {label}
    </span>
  );
};
