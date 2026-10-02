// ============================================================
// VisionQC Frontend Type Definitions
// Keep in sync with backend Pydantic schemas
// ============================================================

export type Decision = 'PASS' | 'FAIL' | 'REVIEW';
export type Severity = 'low' | 'medium' | 'high';
export type ModelStatus = 'not_available' | 'training' | 'ready' | 'validation_required';
export type ClientType = 'web' | 'mobile';

export interface DefectRegion {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface Defect {
  type: string;
  description?: string;
  severity: Severity;
  region?: DefectRegion;
}

export interface ProductSummary {
  id: string;
  name: string;
}

export interface Product {
  id: string;
  name: string;
  code: string;
  description?: string;
  threshold: number;
  model_status: ModelStatus;
  reference_image_count: number;
  created_at: string;
  updated_at: string;
}

export interface ProductCreate {
  name: string;
  code: string;
  description?: string;
  threshold: number;
}

export interface ProductUpdate {
  name?: string;
  code?: string;
  description?: string;
  threshold?: number;
}

export interface ReferenceImage {
  id: string;
  product_id: string;
  storage_url: string;
  is_active: boolean;
  created_at: string;
}

export interface InspectionResponse {
  inspection_id: string;
  product?: ProductSummary;
  decision: Decision;
  anomaly_score: number;
  confidence: number;
  threshold: number;
  heatmap_url?: string;
  original_image_url?: string;
  defects: Defect[];
  summary: string;
  processing_time_ms: number;
  created_at: string;
}

export interface InspectionListItem {
  inspection_id: string;
  product?: ProductSummary;
  decision: Decision;
  anomaly_score: number;
  confidence: number;
  threshold: number;
  heatmap_url?: string;
  original_image_url?: string;
  processing_time_ms: number;
  created_at: string;
}

export interface InspectionListResponse {
  items: InspectionListItem[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface TodayAnalytics {
  total: number;
  passed: number;
  failed: number;
  review: number;
  rejection_rate: number;
  average_anomaly_score: number;
  average_processing_time_ms: number;
}

export interface DailyStats {
  date: string;
  total: number;
  passed: number;
  failed: number;
  review: number;
  rejection_rate: number;
  average_anomaly_score: number;
  average_processing_time_ms: number;
}

export interface ProductDistribution {
  product_id?: string;
  product_name: string;
  total: number;
  failed: number;
}

export interface AnalyticsResponse {
  daily_stats: DailyStats[];
  total_inspections: number;
  total_passed: number;
  total_failed: number;
  total_review: number;
  overall_rejection_rate: number;
  average_anomaly_score: number;
  average_processing_time_ms: number;
  product_distribution: ProductDistribution[];
}

export interface SystemStatus {
  inspection_available: boolean;
  database_available: boolean;
  storage_available: boolean;
}
