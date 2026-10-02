import React, { useEffect, useRef, useState, useCallback } from 'react';
import Webcam from 'react-webcam';
import { Camera, Upload, ScanLine, RefreshCw, AlertCircle } from 'lucide-react';
import { getProducts } from '../api/products';
import { runInspection } from '../api/inspections';
import type { Product, InspectionResponse } from '../types';
import { AnomalyHeatmapViewer } from '../components/inspection/AnomalyHeatmapViewer';
import { InspectionResultCard } from '../components/inspection/InspectionResultCard';

type Stage = 'idle' | 'camera' | 'preview' | 'inspecting' | 'result' | 'error';

export const InspectionPage: React.FC = () => {
  const webcamRef = useRef<Webcam>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [stage, setStage] = useState<Stage>('idle');
  const [products, setProducts] = useState<Product[]>([]);
  const [selectedProduct, setSelectedProduct] = useState<string>('');
  const [capturedImage, setCapturedImage] = useState<string | null>(null);
  const [imageFile, setImageFile] = useState<File | null>(null);
  const [result, setResult] = useState<InspectionResponse | null>(null);
  const [error, setError] = useState<string>('');
  const [cameraError, setCameraError] = useState(false);

  useEffect(() => {
    getProducts().then(setProducts).catch(console.error);
  }, []);

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
    setImageFile(file);
    const reader = new FileReader();
    reader.onload = (ev) => {
      setCapturedImage(ev.target?.result as string);
      setStage('preview');
    };
    reader.readAsDataURL(file);
    e.target.value = '';
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
    setStage('idle');
    setCapturedImage(null);
    setImageFile(null);
    setResult(null);
    setError('');
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-vqc-text">Live Inspection</h1>
        <p className="text-vqc-muted text-sm mt-1">Capture or upload a product image to run quality inspection</p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
        {/* Left: Camera/Preview */}
        <div className="lg:col-span-3 space-y-4">
          {/* Camera view */}
          <div className="card">
            <div className="aspect-video bg-vqc-panel rounded-lg overflow-hidden flex items-center justify-center relative">
              {stage === 'camera' && !cameraError && (
                <Webcam
                  ref={webcamRef}
                  screenshotFormat="image/jpeg"
                  className="w-full h-full object-cover"
                  onUserMediaError={() => setCameraError(true)}
                />
              )}
              {stage === 'camera' && cameraError && (
                <div className="text-center text-vqc-muted">
                  <AlertCircle className="w-8 h-8 mx-auto mb-2 text-vqc-fail" />
                  <p className="text-sm">Camera access denied or unavailable.</p>
                  <p className="text-xs mt-1">Use file upload instead.</p>
                </div>
              )}
              {(stage === 'preview' || stage === 'inspecting' || stage === 'result' || stage === 'error') && capturedImage && (
                <img src={capturedImage} alt="Preview" className="w-full h-full object-contain" />
              )}
              {stage === 'inspecting' && (
                <div className="absolute inset-0 bg-vqc-bg/80 flex flex-col items-center justify-center">
                  <div className="spinner w-10 h-10 mb-3" />
                  <p className="text-vqc-text font-medium">Inspecting unit...</p>
                  <p className="text-vqc-muted text-sm mt-1">Analyzing image</p>
                </div>
              )}
              {stage === 'idle' && (
                <div className="text-center text-vqc-muted">
                  <Camera className="w-12 h-12 mx-auto mb-3 opacity-40" />
                  <p className="text-sm">Camera preview will appear here</p>
                </div>
              )}
            </div>

            {/* Controls */}
            <div className="flex gap-3 mt-4">
              {stage === 'idle' && (
                <>
                  <button onClick={startCamera} className="btn-primary flex items-center gap-2 flex-1">
                    <Camera className="w-4 h-4" /> Start Camera
                  </button>
                  <button
                    onClick={() => fileInputRef.current?.click()}
                    className="btn-secondary flex items-center gap-2 flex-1"
                  >
                    <Upload className="w-4 h-4" /> Upload Image
                  </button>
                </>
              )}
              {stage === 'camera' && !cameraError && (
                <>
                  <button onClick={capturePhoto} className="btn-primary flex items-center gap-2 flex-1">
                    <Camera className="w-4 h-4" /> Capture
                  </button>
                  <button onClick={() => fileInputRef.current?.click()} className="btn-secondary flex items-center gap-2">
                    <Upload className="w-4 h-4" /> Upload
                  </button>
                  <button onClick={reset} className="btn-secondary"><RefreshCw className="w-4 h-4" /></button>
                </>
              )}
              {(stage === 'preview' || stage === 'error') && (
                <>
                  <button onClick={inspect} className="btn-primary flex items-center gap-2 flex-1">
                    <ScanLine className="w-4 h-4" /> INSPECT
                  </button>
                  <button onClick={reset} className="btn-secondary flex items-center gap-2">
                    <RefreshCw className="w-4 h-4" /> Retake
                  </button>
                </>
              )}
              {stage === 'result' && (
                <button onClick={reset} className="btn-secondary flex items-center gap-2 flex-1">
                  <RefreshCw className="w-4 h-4" /> Inspect Another Unit
                </button>
              )}
            </div>

            <input
              ref={fileInputRef}
              type="file"
              accept="image/jpeg,image/png,image/webp"
              className="hidden"
              onChange={handleFileUpload}
            />
          </div>

          {/* Product selector */}
          <div className="card">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="label">Product</label>
                <select
                  aria-label="Product"
                  value={selectedProduct}
                  onChange={(e) => setSelectedProduct(e.target.value)}
                  className="input"
                >
                  <option value="">Select Product</option>
                  {products.map(p => (
                    <option key={p.id} value={p.id}>{p.name} — {p.code}{p.model_status === 'ready' ? ' · Profile ready' : ''}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="label">Sensitivity Threshold</label>
                <div className="input flex items-center text-vqc-text bg-vqc-panel cursor-default">
                  {selectedProductData
                    ? selectedProductData.threshold.toFixed(2)
                    : 'Default (0.55)'}
                </div>
              </div>
            </div>
            <p className="text-xs text-vqc-muted mt-3">For a trained profile, choose the product that matches the uploaded image.</p>
          </div>

          {/* Error */}
          {stage === 'error' && error && (
            <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-4 flex items-start gap-3">
              <AlertCircle className="w-5 h-5 text-red-400 flex-shrink-0 mt-0.5" />
              <p className="text-red-300 text-sm">{error}</p>
            </div>
          )}
        </div>

        {/* Right: Results */}
        <div className="lg:col-span-2 space-y-4">
          {stage === 'result' && result ? (
            <>
              <AnomalyHeatmapViewer
                originalUrl={result.original_image_url}
                heatmapUrl={result.heatmap_url}
              />
              <InspectionResultCard result={result} onInspectNext={reset} />
            </>
          ) : (
            <div className="card h-64 flex items-center justify-center">
              <div className="text-center text-vqc-muted">
                <ScanLine className="w-10 h-10 mx-auto mb-3 opacity-40" />
                <p className="text-sm">Inspection results will appear here</p>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
