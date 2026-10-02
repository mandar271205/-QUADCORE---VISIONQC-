import React from 'react';

export const SettingsPage: React.FC = () => {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-vqc-text">Settings</h1>
        <p className="text-vqc-muted text-sm mt-1">Application configuration</p>
      </div>

      <div className="card max-w-xl">
        <h3 className="section-title">Backend Connection</h3>
        <div>
          <label className="label">API Base URL</label>
          <input
            className="input"
            value={import.meta.env.VITE_API_URL || '/api/v1'}
            readOnly
          />
          <p className="text-vqc-muted text-xs mt-1">
            Set <code className="font-mono bg-vqc-panel px-1 rounded">VITE_API_URL</code> in{' '}
            <code className="font-mono bg-vqc-panel px-1 rounded">web/.env.local</code> to override.
          </p>
        </div>
      </div>

      <div className="card max-w-xl">
        <h3 className="section-title">About VisionQC</h3>
        <div className="space-y-2 text-sm">
          <div className="flex justify-between">
            <span className="text-vqc-muted">Version</span>
            <span className="text-vqc-text font-mono">1.0.0</span>
          </div>
          <div className="flex justify-between">
            <span className="text-vqc-muted">Mode</span>
            <span className="text-vqc-text font-mono">Production</span>
          </div>
        </div>
      </div>
    </div>
  );
};
