import React, { useEffect, useState } from 'react';
import { NavLink } from 'react-router-dom';
import apiClient from '../../api/client';
import { getProducts } from '../../api/products';
import {
  LayoutDashboard,
  ScanLine,
  Package,
  ClipboardList,
  BarChart2,
  Settings,
  Eye,
  Inbox
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { useQuery } from '@tanstack/react-query';
import { reviewsApi } from '../../api/reviews';

function prepareInspection() {
  void import('../../pages/InspectionPage').catch(() => {});
  void getProducts().catch(() => {});
}

const navItems = [
  { to: '/', icon: LayoutDashboard, label: 'Dashboard' },
  { to: '/inspect', icon: ScanLine, label: 'Live Inspection' },
  { to: '/products', icon: Package, label: 'Products' },
  { to: '/reviews', icon: Inbox, label: 'Review Queue', badge: true },
  { to: '/history', icon: ClipboardList, label: 'History' },
  { to: '/analytics', icon: BarChart2, label: 'Analytics' },
  { to: '/comparison', icon: BarChart2, label: 'Model Comparison' },
  { to: '/settings', icon: Settings, label: 'Settings' },
];

export const Sidebar: React.FC = () => {
  const [status, setStatus] = useState<'CHECKING' | 'READY' | 'UNAVAILABLE'>('CHECKING');
  
  const { data: reviewCount } = useQuery({
    queryKey: ['reviewCount'],
    queryFn: () => reviewsApi.getReviewCount(),
    refetchInterval: 30000,
  });

  useEffect(() => {
    let active = true;
    const check = () => apiClient.get<{inspection_available:boolean}>('/system/status')
      .then(response => { if (active) setStatus(response.data.inspection_available ? 'READY' : 'UNAVAILABLE'); })
      .catch(() => { if (active) setStatus('UNAVAILABLE'); });
    check();
    const timer = window.setInterval(check, 30000);
    return () => { active = false; window.clearInterval(timer); };
  }, []);
  return (
    <aside className="w-[240px] flex-shrink-0 min-h-screen bg-card border-r border-border flex flex-col z-20">
      {/* Logo */}
      <div className="h-16 flex items-center px-6 border-b border-border">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 bg-primary rounded flex items-center justify-center shadow-sm shadow-primary/20">
            <Eye className="w-4 h-4 text-primary-foreground" />
          </div>
          <div>
            <h1 className="text-foreground font-bold text-sm tracking-widest uppercase">VisionQC</h1>
          </div>
        </div>
      </div>

      {/* Nav */}
      <nav className="flex-1 px-3 py-6 space-y-1 overflow-y-auto">
        {navItems.map(({ to, icon: Icon, label, badge }) => (
          <NavLink
            key={to}
            to={to}
            end={to === '/'}
            onPointerEnter={to === '/inspect' ? prepareInspection : undefined}
            onFocus={to === '/inspect' ? prepareInspection : undefined}
            className={({ isActive }) =>
              cn(
                "flex items-center justify-between px-3 py-2.5 rounded-md text-sm font-medium transition-all duration-200 group",
                isActive
                  ? "bg-primary/10 text-primary"
                  : "text-muted-foreground hover:text-foreground hover:bg-secondary/80"
              )
            }
          >
            {({ isActive }) => (
              <>
                <div className="flex items-center gap-3">
                  <Icon className={cn("w-4 h-4 flex-shrink-0 transition-colors", isActive ? "text-primary" : "text-muted-foreground group-hover:text-foreground")} />
                  {label}
                </div>
                {badge && reviewCount && reviewCount.pending > 0 && (
                  <span className="bg-amber-500 text-white text-[10px] font-bold px-1.5 py-0.5 rounded-full">
                    {reviewCount.pending}
                  </span>
                )}
              </>
            )}
          </NavLink>
        ))}
      </nav>

      {/* System status at bottom */}
      <div className="p-4 border-t border-border bg-card/50">
        <div className="text-xs text-muted-foreground mb-1 font-medium uppercase tracking-wider">Status</div>
        <div className="flex items-center gap-3">
          <div
            className={`w-2 h-2 rounded-full ${
              status === 'READY'
                ? 'bg-green-500 shadow-[0_0_8px_rgba(34,197,94,0.5)]'
                : 'bg-amber-500 shadow-[0_0_8px_rgba(245,158,11,0.4)]'
            }`}
          />

          <div className="flex flex-col">
            <span className="text-sm font-medium text-foreground">
              Inspection System
            </span>

            <span
              className={`text-xs font-semibold ${
                status === 'READY'
                  ? 'text-green-500'
                  : 'text-amber-500'
              }`}
            >
              {status}
            </span>
          </div>
        </div>
      </div>
    </aside>
  );
};
