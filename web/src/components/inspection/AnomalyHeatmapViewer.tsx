import React, { useState } from 'react';
import { Layers, Image as ImageIcon, Activity } from 'lucide-react';

interface Props {
  originalUrl?: string;
  heatmapUrl?: string;
  className?: string;
}

type ViewMode = 'original' | 'heatmap' | 'overlay';

export const AnomalyHeatmapViewer: React.FC<Props> = ({
  originalUrl,
  heatmapUrl,
  className = '',
}) => {
  const [mode, setMode] = useState<ViewMode>('overlay');
  const [opacity, setOpacity] = useState(0.55);

  const modes: { id: ViewMode; icon: React.ElementType; label: string }[] = [
    { id: 'original', icon: ImageIcon, label: 'Original' },
    { id: 'heatmap', icon: Activity, label: 'Heatmap' },
    { id: 'overlay', icon: Layers, label: 'Overlay' },
  ];

  const hasImages = originalUrl || heatmapUrl;

  return (
    <div className={`card ${className}`}>
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold text-vqc-text">Anomaly Heatmap</h3>
        {hasImages && (
          <div className="flex items-center gap-1 bg-vqc-panel rounded-lg p-1">
            {modes.map(({ id, icon: Icon, label }) => (
              <button
                key={id}
                onClick={() => setMode(id)}
                className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-md text-xs font-medium transition-colors ${
                  mode === id
                    ? 'bg-vqc-accent text-white'
                    : 'text-vqc-muted hover:text-vqc-text'
                }`}
              >
                <Icon className="w-3 h-3" />
                {label}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Image display */}
      <div className="relative rounded-lg overflow-hidden bg-vqc-panel aspect-video flex items-center justify-center">
        {!hasImages ? (
          <div className="text-vqc-muted text-sm">No image available</div>
        ) : (
          <div className="relative w-full h-full">
            {/* Original */}
            {originalUrl && (
              <img
                src={originalUrl}
                alt="Original inspection image"
                className={`absolute inset-0 w-full h-full object-contain transition-opacity duration-200 ${
                  mode === 'original' || mode === 'overlay' ? 'opacity-100' : 'opacity-0'
                }`}
              />
            )}

            {/* Heatmap overlay */}
            {heatmapUrl && (
              <img
                src={heatmapUrl}
                alt="Anomaly heatmap"
                className={`absolute inset-0 w-full h-full object-contain transition-opacity duration-200`}
                style={{
                  opacity:
                    mode === 'heatmap' ? 1 :
                    mode === 'overlay' ? opacity :
                    0,
                  mixBlendMode: mode === 'overlay' ? 'screen' : 'normal',
                }}
              />
            )}
          </div>
        )}
      </div>

      {/* Opacity slider - only for overlay mode */}
      {mode === 'overlay' && heatmapUrl && originalUrl && (
        <div className="mt-4 flex items-center gap-3">
          <span className="text-vqc-muted text-xs w-20">Heatmap opacity</span>
          <input
            type="range"
            min={0}
            max={1}
            step={0.05}
            value={opacity}
            onChange={(e) => setOpacity(Number(e.target.value))}
            className="flex-1 accent-vqc-accent"
          />
          <span className="text-vqc-muted text-xs w-10 text-right">
            {Math.round(opacity * 100)}%
          </span>
        </div>
      )}
    </div>
  );
};
