import React, { Suspense } from 'react';
import { Outlet } from 'react-router-dom';
import { Sidebar } from './Sidebar';
import { Topbar } from './Topbar';

export const Layout: React.FC = () => {
  return (
    <div className="flex h-screen overflow-hidden bg-background text-foreground font-sans">
      <Sidebar />
      <div className="flex-1 flex flex-col h-full overflow-hidden relative">
        <Topbar />
        <main className="flex-1 overflow-y-auto bg-background/50">
          <div className="p-6 md:p-8 min-h-full max-w-[1920px] mx-auto">
            <Suspense fallback={
              <div role="status" className="flex items-center justify-center h-64 gap-3 text-muted-foreground">
                <div className="spinner w-6 h-6" /> Loading page…
              </div>
            }>
              <Outlet />
            </Suspense>
          </div>
        </main>
      </div>
    </div>
  );
};
