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
  const [mode, setMode] = useState<string>('overlay');
  const [opacity, setOpacity] = useState<number[]>([55]);

  const hasImages = originalUrl || heatmapUrl;

  return (
    <Card className={`border-border bg-card shadow-lg ${className}`}>
      <CardHeader className="flex flex-row items-center justify-between pb-2 space-y-0">
        <CardTitle className="text-sm font-semibold tracking-tight uppercase">Anomaly Heatmap</CardTitle>
        {hasImages && (
          <Tabs value={mode} onValueChange={setMode} className="w-auto">
            <TabsList className="grid w-[240px] grid-cols-3">
              <TabsTrigger value="original" className="text-xs">
                <ImageIcon className="w-3 h-3 mr-1" />
                Original
              </TabsTrigger>
              <TabsTrigger value="heatmap" className="text-xs">
                <Activity className="w-3 h-3 mr-1" />
                Heatmap
              </TabsTrigger>
              <TabsTrigger value="overlay" className="text-xs">
                <Layers className="w-3 h-3 mr-1" />
                Overlay
              </TabsTrigger>
            </TabsList>
          </Tabs>
        )}
      </CardHeader>
      
      <CardContent className="pt-2">
        <div className="relative rounded-md overflow-hidden bg-muted/30 aspect-video flex items-center justify-center border border-border">
          {!hasImages ? (
            <div className="text-muted-foreground text-sm flex flex-col items-center">
              <Activity className="w-8 h-8 mb-2 opacity-20" />
              <span>No image available</span>
            </div>
          ) : (
            <div className="relative w-full h-full bg-black/50">
              {/* Original */}
              {originalUrl && (
                <img
                  src={originalUrl}
                  alt="Original inspection image"
                  className={`absolute inset-0 w-full h-full object-contain transition-opacity duration-300 ${
                    mode === 'original' || mode === 'overlay' ? 'opacity-100' : 'opacity-0'
                  }`}
                />
              )}

              {/* Heatmap overlay */}
              {heatmapUrl && (
                <img
                  src={heatmapUrl}
                  alt="Anomaly heatmap"
                  className={`absolute inset-0 w-full h-full object-contain transition-opacity duration-300`}
                  style={{
                    opacity:
                      mode === 'heatmap' ? 1 :
                      mode === 'overlay' ? opacity[0] / 100 :
                      0,
                    mixBlendMode: mode === 'overlay' ? 'screen' : 'normal',
                  }}
                />
              )}
            </div>
          )}
        </div>

        {/* Opacity slider */}
        {mode === 'overlay' && heatmapUrl && originalUrl && (
          <div className="mt-5 flex items-center gap-4 px-2">
            <span className="text-muted-foreground text-xs font-medium uppercase tracking-wider w-32">Heatmap Opacity</span>
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
