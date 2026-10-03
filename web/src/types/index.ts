// ============================================================
// VisionQC Frontend Type Definitions
// Keep in sync with backend Pydantic schemas
// ============================================================

export type Decision = 'PASS' | 'FAIL' | 'REVIEW' | 'RETAKE';
export type Severity = 'low' | 'medium' | 'high';
export type OperationalSeverity = 'NONE' | 'MINOR' | 'MODERATE' | 'CRITICAL' | 'UNKNOWN';
export type QualityCheckStatus = 'good' | 'uncertain' | 'poor' | 'not_run';
export type ReviewStatus = 'pending' | 'accepted' | 'rejected';
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
  barcode?: string;
}

export interface ProductCreate {
  name: string;
  code: string;
  description?: string;
  threshold: number;
  barcode?: string;
}

export interface ProductUpdate {
  name?: string;
  code?: string;
  description?: string;
  threshold?: number;
  barcode?: string;
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
  
  operational_severity: OperationalSeverity;
  quality_check_status: QualityCheckStatus;
  quality_score?: number;
  quality_issues?: string[];
  quality_message?: string;
  conformity_summary?: string;
  batch_id?: string;
  shift?: string;
  review_status?: ReviewStatus;
  human_decision?: Decision;
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

  operational_severity: OperationalSeverity;
  quality_check_status: QualityCheckStatus;
  batch_id?: string;
  shift?: string;
  review_status?: ReviewStatus;
  human_decision?: Decision;
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
  retake: number;
  rejection_rate: number;
  average_anomaly_score: number;
  average_processing_time_ms: number;
  pending_reviews: number;
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
  total_retake: number;
  overall_rejection_rate: number;
  average_anomaly_score: number;
  average_processing_time_ms: number;
  product_distribution: ProductDistribution[];
  
  review_rate: number;
  override_rate: number;
  severity_distribution: Record<string, number>;
}

export interface HotspotResponse {
  status: string;
  product_id: string;
  grid_size?: number;
  grid?: number[][];
  contributing_inspections: number;
  total_regions: number;
  min_evidence_required?: number;
  date_range?: { from: string; to: string };
  message?: string;
}

export interface DriftStatusItem {
  product_id: string;
  drift_status: string;
  computed_at: string;
  worsening_signals: string[];
  inspection_count: number;
  rejection_rate: number;
}

export interface DriftAllResponse {
  items: DriftStatusItem[];
}

export interface ProfileVersionItem {
  id: string;
  product_id: string;
  version_number: number;
  is_active: boolean;
  reference_image_count: number;
  threshold_snapshot: number;
  model_status_snapshot: string;
  change_reason?: string;
  created_at: string;
  parent_version_id?: string;
}

export interface ProfileVersionListResponse {
  items: ProfileVersionItem[];
  active_version?: number;
}

export interface ReviewDefectSummary {
  type: string;
  description?: string;
  severity: string;
}

export interface PendingReviewItem {
  review_id: string;
  inspection_id: string;
  queued_at: string;
  product?: ProductSummary;
  ai_decision: Decision;
  anomaly_score: number;
  confidence: number;
  threshold: number;
  operational_severity: OperationalSeverity;
  heatmap_url?: string;
  original_image_url?: string;
  conformity_summary?: string;
  defects: ReviewDefectSummary[];
  quality_check_status: QualityCheckStatus;
  quality_message?: string;
  batch_id?: string;
  shift?: string;
  review_status: ReviewStatus;
  reviewed_at?: string;
  human_decision?: Decision;
  note?: string;
}

export interface PendingReviewListResponse {
  items: PendingReviewItem[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface SystemStatus {
  inspection_available: boolean;
  database_available: boolean;
  storage_available: boolean;
}
