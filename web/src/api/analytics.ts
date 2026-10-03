import { readShared } from './reads';
import apiClient from './client';
import type { 
  TodayAnalytics, AnalyticsResponse, HotspotResponse, 
  DriftAllResponse, ProfileVersionListResponse 
} from '../types';

export async function getTodayAnalytics(): Promise<TodayAnalytics> {
  return readShared('/analytics/today', async () => {
    const { data } = await apiClient.get<TodayAnalytics>('/analytics/today');
    return data;
  });
}

export async function getRangeAnalytics(params?: {
  date_from?: string;
  date_to?: string;
  product_id?: string;
}): Promise<AnalyticsResponse> {
  return readShared('/analytics' + JSON.stringify(params || {}), async () => {
    const { data } = await apiClient.get<AnalyticsResponse>('/analytics', { params });
    return data;
  });
}

export async function getSystemStatus() {
  const { data } = await apiClient.get('/system/status');
  return data;
}

export async function getProductHotspots(productId: string, days = 30): Promise<HotspotResponse> {
  const { data } = await apiClient.get<HotspotResponse>('/analytics/hotspots', {
    params: { product_id: productId, days },
  });
  return data;
}

export async function getAllDriftStatus(): Promise<DriftAllResponse> {
  const { data } = await apiClient.get<DriftAllResponse>('/analytics/drift');
  return data;
}

export async function getProductDrift(productId: string) {
  const { data } = await apiClient.get(`/analytics/drift/${productId}`);
  return data;
}

export async function computeProductDrift(productId: string) {
  const { data } = await apiClient.post(`/analytics/drift/${productId}/compute`);
  return data;
}

export async function getProfileVersions(productId: string): Promise<ProfileVersionListResponse> {
  const { data } = await apiClient.get<ProfileVersionListResponse>(`/analytics/profile-versions/${productId}`);
  return data;
}
