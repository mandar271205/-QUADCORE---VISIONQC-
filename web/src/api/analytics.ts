import apiClient from './client';
import type { TodayAnalytics, AnalyticsResponse } from '../types';

export async function getTodayAnalytics(): Promise<TodayAnalytics> {
  const { data } = await apiClient.get<TodayAnalytics>('/analytics/today');
  return data;
}

export async function getRangeAnalytics(params?: {
  date_from?: string;
  date_to?: string;
  product_id?: string;
}): Promise<AnalyticsResponse> {
  const { data } = await apiClient.get<AnalyticsResponse>('/analytics', { params });
  return data;
}

export async function getSystemStatus() {
  const { data } = await apiClient.get('/system/status');
  return data;
}
