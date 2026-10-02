import React from 'react';
import { NavLink, useLocation } from 'react-router-dom';
import {
  LayoutDashboard,
  ScanLine,
  Package,
  ClipboardList,
  BarChart2,
  Settings,
  Eye,
  Zap
} from 'lucide-react';

const navItems = [
  { to: '/', icon: LayoutDashboard, label: 'Dashboard' },
  { to: '/inspect', icon: ScanLine, label: 'Live Inspection' },
  { to: '/products', icon: Package, label: 'Products' },
  { to: '/history', icon: ClipboardList, label: 'History' },
  { to: '/analytics', icon: BarChart2, label: 'Analytics' },
  { to: '/settings', icon: Settings, label: 'Settings' },
];

export const Sidebar: React.FC = () => {
  return (
    <aside className="w-60 min-h-screen bg-vqc-surface border-r border-vqc-border flex flex-col">
      {/* Logo */}
      <div className="px-6 py-5 border-b border-vqc-border">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 bg-vqc-accent rounded-lg flex items-center justify-center">
            <Eye className="w-4 h-4 text-white" />
          </div>
          <div>
            <h1 className="text-white font-bold text-sm tracking-wide">VisionQC</h1>
            <p className="text-vqc-muted text-xs">Quality Inspection</p>
          </div>
        </div>
      </div>

      {/* Nav */}
      <nav className="flex-1 px-3 py-4 space-y-0.5">
        {navItems.map(({ to, icon: Icon, label }) => (
          <NavLink
            key={to}
            to={to}
            end={to === '/'}
            className={({ isActive }) =>
              `flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors duration-150 ${
                isActive
                  ? 'bg-vqc-accent/15 text-vqc-accent border border-vqc-accent/20'
                  : 'text-vqc-muted hover:text-vqc-text hover:bg-vqc-panel'
              }`
            }
          >
            <Icon className="w-4 h-4 flex-shrink-0" />
            {label}
          </NavLink>
        ))}
      </nav>

      {/* System status */}
      <div className="px-4 py-4 border-t border-vqc-border">
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 bg-vqc-pass rounded-full animate-pulse" />
          <span className="text-vqc-muted text-xs">Inspection System</span>
        </div>
        <p className="text-vqc-pass text-xs font-semibold mt-0.5 ml-4">READY</p>
      </div>
    </aside>
  );
};
