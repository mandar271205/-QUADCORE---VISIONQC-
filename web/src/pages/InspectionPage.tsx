import React, { useEffect, useRef, useState, useCallback } from 'react';
import Webcam from 'react-webcam';
import { Camera, Upload, ScanLine, RefreshCw, AlertCircle, Activity } from 'lucide-react';
import { getProducts, resolveProductByCode } from '../api/products';
import { runInspection } from '../api/inspections';
import type { Product, InspectionResponse } from '../types';
import { AnomalyHeatmapViewer } from '../components/inspection/AnomalyHeatmapViewer';
import { InspectionResultCard } from '../components/inspection/InspectionResultCard';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Input } from '@/components/ui/input';

type Stage = 'idle' | 'camera' | 'preview' | 'inspecting' | 'result' | 'error';

export const InspectionPage: React.FC = () => {
  const webcamRef = useRef<Webcam>(null);
  const previewUrlRef = useRef<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [stage, setStage] = useState<Stage>('idle');
  const [products, setProducts] = useState<Product[]>([]);
  const [selectedProduct, setSelectedProduct] = useState<string>('');
  const [capturedImage, setCapturedImage] = useState<string | null>(null);
  const [imageFile, setImageFile] = useState<File | null>(null);
  const [result, setResult] = useState<InspectionResponse | null>(null);
  const [error, setError] = useState<string>('');
  const [cameraError, setCameraError] = useState(false);
  
  const [barcode, setBarcode] = useState('');
  const [resolvingBarcode, setResolvingBarcode] = useState(false);
  const [barcodeMessage, setBarcodeMessage] = useState<{type: 'success'|'error', text: string} | null>(null);

  useEffect(() => {
    getProducts().then(setProducts).catch(console.error);
  }, []);

  useEffect(() => () => {
    if (previewUrlRef.current) URL.revokeObjectURL(previewUrlRef.current);
  }, []);

  const clearPreviewUrl = () => {
    if (previewUrlRef.current) URL.revokeObjectURL(previewUrlRef.current);
    previewUrlRef.current = null;
  };

  const selectedProductData = products.find(p => p.id === selectedProduct);

  const startCamera = () => {
    setCameraError(false);
    setStage('camera');
  };

  const capturePhoto = useCallback(() => {
    const screenshot = webcamRef.current?.getScreenshot();
    if (screenshot) {
      setCapturedImage(screenshot);
      // Convert base64 to File
      fetch(screenshot)
        .then(r => r.blob())
        .then(blob => {
          const file = new File([blob], 'capture.jpg', { type: 'image/jpeg' });
          setImageFile(file);
          setStage('preview');
        });
    }
  }, []);

  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    clearPreviewUrl();
    previewUrlRef.current = URL.createObjectURL(file);
    setImageFile(file);
    setCapturedImage(previewUrlRef.current);
    setStage('preview');
    e.target.value = '';
  };

  const handleBarcodeSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!barcode.trim()) return;
    
    setResolvingBarcode(true);
    setBarcodeMessage(null);
    try {
      const res = await resolveProductByCode(barcode.trim());
      if (res.product) {
        setSelectedProduct(res.product.id);
        setBarcodeMessage({ type: 'success', text: `Resolved: ${res.product.name}` });
      } else {
        setSelectedProduct('none');
        setBarcodeMessage({ type: 'error', text: res.message || 'Product not found' });
      }
    } catch (e: any) {
      setBarcodeMessage({ type: 'error', text: 'Failed to resolve barcode' });
    } finally {
      setResolvingBarcode(false);
    }
  };

  const inspect = async () => {
    if (!imageFile) return;
    setStage('inspecting');
    setError('');
    try {
      const res = await runInspection(imageFile, selectedProduct || undefined, 'web');
      setResult(res);
      setStage('result');
    } catch (e: any) {
      setError(e.message || 'Inspection could not be completed. Please try again.');
      setStage('error');
    }
  };

  const reset = () => {
    clearPreviewUrl();
    setStage('idle');
    setCapturedImage(null);
    setImageFile(null);
    setResult(null);
    setError('');
    setBarcode('');
    setBarcodeMessage(null);
  };

  return (
    <div className="space-y-6 max-w-[1600px] mx-auto">
      <div>
        <h1 className="text-3xl font-bold tracking-tight text-foreground">Live Inspection</h1>
        <p className="text-muted-foreground mt-1">Capture or upload a product image to run AI-powered quality inspection</p>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-5 gap-6">
        {/* Left: Camera/Preview */}
        <div className="xl:col-span-3 flex flex-col gap-6">
          <Card className="flex-1 shadow-md border-border bg-card overflow-hidden">
            <CardHeader className="bg-secondary/30 pb-4 border-b border-border">
              <CardTitle className="text-sm uppercase tracking-widest font-semibold flex items-center gap-2">
                <Camera className="w-4 h-4 text-primary" /> Camera Feed
              </CardTitle>
            </CardHeader>
            <CardContent className="p-4">
              <div className="aspect-video bg-black/60 rounded-md overflow-hidden flex items-center justify-center relative border border-border">
                {stage === 'camera' && !cameraError && (
                  <Webcam
                    ref={webcamRef}
                    screenshotFormat="image/jpeg"
                    className="w-full h-full object-cover"
                    onUserMediaError={() => setCameraError(true)}
                  />
                )}
                {stage === 'camera' && cameraError && (
                  <div className="text-center text-muted-foreground">
                    <AlertCircle className="w-10 h-10 mx-auto mb-3 text-destructive" />
                    <p className="font-medium">Camera access denied or unavailable</p>
                    <p className="text-xs mt-1">Use file upload instead</p>
                  </div>
                )}
                {(stage === 'preview' || stage === 'inspecting' || stage === 'result' || stage === 'error') && capturedImage && (
                  <img decoding="async" src={capturedImage} alt="Preview" className="w-full h-full object-contain" />
                )}
                {stage === 'inspecting' && (
                  <div className="absolute inset-0 bg-background/80 backdrop-blur-sm flex flex-col items-center justify-center">
                    <div className="relative">
                      <div className="spinner w-12 h-12 mb-4 border-primary/20 border-t-primary" />
                      <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
                        <ScanLine className="w-4 h-4 text-primary animate-pulse" />
                      </div>
                    </div>
                    <p className="text-foreground font-semibold tracking-wide">ANALYZING UNIT...</p>
                    <p className="text-muted-foreground text-sm mt-1">Running deep inspection</p>
                  </div>
                )}
                {stage === 'idle' && (
                  <div className="text-center text-muted-foreground/60">
                    <ScanLine className="w-16 h-16 mx-auto mb-4 opacity-50" />
                    <p className="text-sm uppercase tracking-widest font-medium">System Idle</p>
                  </div>
                )}
              </div>

              {/* Controls */}
              <div className="flex gap-3 mt-4">
                {stage === 'idle' && (
                  <>
                    <Button onClick={startCamera} size="lg" className="flex-1 font-semibold tracking-wide">
                      <Camera className="w-4 h-4 mr-2" /> Start Camera
                    </Button>
                    <Button
                      onClick={() => fileInputRef.current?.click()}
                      variant="outline" size="lg" className="flex-1 font-semibold tracking-wide"
                    >
                      <Upload className="w-4 h-4 mr-2" /> Upload Image
                    </Button>
                  </>
                )}
                {stage === 'camera' && !cameraError && (
                  <>
                    <Button onClick={capturePhoto} size="lg" className="flex-1 font-semibold tracking-wide">
                      <Camera className="w-4 h-4 mr-2" /> Capture Frame
                    </Button>
                    <Button onClick={() => fileInputRef.current?.click()} variant="outline" size="lg">
                      <Upload className="w-4 h-4 mr-2" /> Upload
                    </Button>
                    <Button onClick={reset} variant="ghost" size="lg" className="px-4">
                      <RefreshCw className="w-4 h-4" />
                    </Button>
                  </>
                )}
                {(stage === 'preview' || stage === 'error') && (
                  <>
                    <Button onClick={inspect} size="lg" className="flex-1 font-bold tracking-widest bg-primary hover:bg-primary/90 text-primary-foreground">
                      <ScanLine className="w-5 h-5 mr-2" /> RUN INSPECTION
                    </Button>
                    <Button onClick={reset} variant="outline" size="lg">
                      <RefreshCw className="w-4 h-4 mr-2" /> Retake
                    </Button>
                  </>
                )}
                {stage === 'result' && (
                  <Button onClick={reset} size="lg" variant="outline" className="flex-1 font-semibold tracking-wide">
                    <RefreshCw className="w-4 h-4 mr-2" /> Inspect Another Unit
                  </Button>
                )}
              </div>

              <input
                ref={fileInputRef}
                type="file"
                accept="image/jpeg,image/png,image/webp"
                className="hidden"
                onChange={handleFileUpload}
              />
            </CardContent>
          </Card>

          {/* Product selector */}
          <Card className="shadow-md border-border bg-card">
            <CardContent className="p-4">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                {/* Target Product */}
                <div className="space-y-2">
                  <label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground flex justify-between items-center">
                    <span>Target Product</span>
                    {barcodeMessage && (
                      <span className={`text-[10px] px-1.5 py-0.5 rounded ${barcodeMessage.type === 'success' ? 'bg-green-500/20 text-green-500' : 'bg-red-500/20 text-red-500'}`}>
                        {barcodeMessage.text}
                      </span>
                    )}
                  </label>
                  
                  <div className="flex gap-2 mb-2">
                    <form onSubmit={handleBarcodeSubmit} className="flex-1 flex gap-2">
                      <Input 
                        placeholder="Scan Barcode / QR..." 
                        value={barcode}
                        onChange={e => setBarcode(e.target.value)}
                        className="bg-secondary/30 h-11 text-sm font-mono"
                        disabled={resolvingBarcode}
                      />
                      <Button type="submit" variant="secondary" className="h-11 px-3" disabled={resolvingBarcode || !barcode}>
                        {resolvingBarcode ? <RefreshCw className="w-4 h-4 animate-spin" /> : <ScanLine className="w-4 h-4" />}
                      </Button>
                    </form>
                  </div>

                  <Select
                    value={selectedProduct || 'none'}
                    onValueChange={value => setSelectedProduct(value === 'none' ? '' : value)}
                  >
                    <SelectTrigger className="bg-secondary/50 border-border h-11">
                      <SelectValue placeholder="Select Product (optional)" />
                    </SelectTrigger>

                    <SelectContent>
                      <SelectItem
                        value="none"
                        className="text-muted-foreground italic"
                      >
                        None (Auto-detect)
                      </SelectItem>

                      {products.map((p) => (
                        <SelectItem key={p.id} value={p.id}>
                          {p.name} — {p.code}
                          {p.model_status === 'ready' ? ' · Profile ready' : ''}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                {/* Detection Sensitivity */}
                <div className="space-y-2">
                  <label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                    Detection Sensitivity
                  </label>

                  <div className="h-11 px-3 flex items-center bg-secondary/30 border border-border/50 rounded-md text-sm text-foreground/80 font-medium">
                    {selectedProductData
                      ? `${selectedProductData.threshold.toFixed(2)} (Product specific)`
                      : 'Default (0.55)'}
                  </div>
                </div>
              </div>

              <p className="text-xs text-muted-foreground mt-3 leading-relaxed">
                For a trained profile, choose the product that matches the uploaded image.
              </p>
            </CardContent>
          </Card>

          {/* Error */}
          {stage === 'error' && error && (
            <Alert variant="destructive" className="bg-destructive/10 border-destructive/20 text-destructive-foreground">
              <AlertCircle className="h-4 w-4" />
              <AlertDescription className="font-medium ml-2">{error}</AlertDescription>
            </Alert>
          )}
        </div>

        {/* Right: Results */}
        <div className="xl:col-span-2 flex flex-col gap-6">
          {stage === 'result' && result ? (
            <>
              <AnomalyHeatmapViewer
                originalUrl={result.original_image_url}
                heatmapUrl={result.heatmap_url}
              />
              <InspectionResultCard result={result} onInspectNext={reset} />
            </>
          ) : (
            <Card className="h-full min-h-[400px] border-dashed border-2 border-border/50 bg-transparent flex items-center justify-center shadow-none">
              <CardContent className="flex flex-col items-center justify-center p-6 text-center">
                <div className="w-16 h-16 rounded-full bg-secondary/50 flex items-center justify-center mb-4 border border-border">
                  <Activity className="w-8 h-8 text-muted-foreground/50" />
                </div>
                <h3 className="font-semibold text-lg text-foreground mb-1 tracking-tight">Awaiting Telemetry</h3>
                <p className="text-muted-foreground text-sm max-w-[250px]">
                  Inspection results, anomaly maps, and final decisions will appear here
                </p>
              </CardContent>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
};
