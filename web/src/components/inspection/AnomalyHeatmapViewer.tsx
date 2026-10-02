import React, { useState } from 'react';
import { Layers, Image as ImageIcon, Activity } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Slider } from '@/components/ui/slider';

interface Props {
  originalUrl?: string;
  heatmapUrl?: string;
  className?: string;
}

export const AnomalyHeatmapViewer: React.FC<Props> = ({
  originalUrl,
  heatmapUrl,
  className = '',
}) => {
  const [mode, setMode] = useState<'original' | 'heatmap' | 'overlay'>('overlay');
  const [opacity, setOpacity] = useState<number[]>([60]);

  const hasImages = Boolean(originalUrl || heatmapUrl);

  return (
    <Card className={`border-border bg-card shadow-lg ${className}`}>
      <CardHeader className="flex flex-row items-center justify-between pb-2 space-y-0">
        <CardTitle className="text-sm font-semibold tracking-tight uppercase">
          Anomaly Heatmap
        </CardTitle>

        {hasImages && (
          <Tabs
            value={mode}
            onValueChange={(value: string) =>
              setMode(value as 'original' | 'heatmap' | 'overlay')
            }
            className="w-auto"
          >
            <TabsList>
              <TabsTrigger value="original">Original</TabsTrigger>
              <TabsTrigger value="heatmap">Heatmap</TabsTrigger>
              <TabsTrigger value="overlay">Overlay</TabsTrigger>
            </TabsList>
          </Tabs>
        )}
      </CardHeader>

      <CardContent>
        {/* Image display */}
        <div className="relative rounded-lg overflow-hidden bg-muted aspect-video flex items-center justify-center">
          {!hasImages ? (
            <div className="text-muted-foreground text-sm">
              No image available
            </div>
          ) : (
            <div className="relative w-full h-full">
              {/* Original inspection image */}
              {originalUrl && (
                <img
                  src={originalUrl}
                  alt="Original inspection image"
                  className={`absolute inset-0 w-full h-full object-contain transition-opacity duration-300 ${
                    mode === 'original' || mode === 'overlay'
                      ? 'opacity-100'
                      : 'opacity-0'
                  }`}
                />
              )}

              {/* Anomaly heatmap */}
              {heatmapUrl && (
                <img
                  src={heatmapUrl}
                  alt="Anomaly heatmap"
                  className="absolute inset-0 w-full h-full object-contain transition-opacity duration-300"
                  style={{
                    opacity:
                      mode === 'heatmap'
                        ? 1
                        : mode === 'overlay'
                          ? opacity[0] / 100
                          : 0,
                    mixBlendMode: mode === 'overlay' ? 'screen' : 'normal',
                  }}
                />
              )}
            </div>
          )}
        </div>

        {/* Heatmap opacity — only relevant in overlay mode */}
        {mode === 'overlay' && heatmapUrl && originalUrl && (
          <div className="mt-5 flex items-center gap-4 px-2">
            <span className="text-muted-foreground text-xs font-medium uppercase tracking-wider w-32">
              Heatmap Opacity
            </span>

            <Slider
              value={opacity}
              onValueChange={setOpacity}
              max={100}
              step={5}
              className="flex-1"
            />

            <span className="text-muted-foreground text-xs font-medium w-10 text-right">
              {opacity[0]}%
            </span>
          </div>
        )}
      </CardContent>
    </Card>
  );
};
