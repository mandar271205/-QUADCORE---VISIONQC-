import React from 'react';
import { useLocation } from 'react-router-dom';

export const Topbar: React.FC = () => {
  const location = useLocation();
  
  // Basic route to title mapping
  const getPageTitle = () => {
    const path = location.pathname;
    if (path === '/') return 'Dashboard';
    if (path === '/inspect') return 'Live Inspection';
    if (path.startsWith('/products')) return 'Products';
    if (path.startsWith('/history')) return 'Inspection History';
    if (path === '/analytics') return 'Analytics';
    if (path === '/settings') return 'Settings';
    return 'VisionQC';
  };

  return (
    <header className="h-16 flex-shrink-0 border-b border-border bg-card/50 backdrop-blur-sm flex items-center justify-between px-6 z-10">
      <div className="flex items-center">
        <h2 className="text-lg font-semibold tracking-tight">{getPageTitle()}</h2>
      </div>
      <div className="flex items-center gap-4">
        <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-secondary/50 border border-border">
          <div className="w-2 h-2 rounded-full bg-green-500 animate-pulse" />
          <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">System Ready</span>
        </div>
      </div>
    </header>
  );
};
