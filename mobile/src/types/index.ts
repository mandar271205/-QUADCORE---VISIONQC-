// Shared types - mirrors backend Pydantic schemas
export type Decision = 'PASS' | 'FAIL' | 'REVIEW';
export type Severity = 'low' | 'medium' | 'high';

export interface Defect {
  type: string;
  description?: string;
  severity: Severity;
  region?: { x: number; y: number; width: number; height: number };
}

export interface Product {
  id: string;
  name: string;
  code: string;
  description?: string;
  threshold: number;
  model_status?: 'not_available' | 'training' | 'ready' | 'validation_required';
  reference_image_count?: number;
}

export interface InspectionResponse {
  inspection_id: string;
  product?: { id: string; name: string };
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
  product?: { id: string; name: string };
  decision: Decision;
  anomaly_score: number;
  confidence: number;
  threshold: number;
  heatmap_url?: string;
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
