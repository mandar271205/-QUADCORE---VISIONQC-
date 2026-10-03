import { apiClient } from './client';
import type { InspectionResponse, InspectionListResponse } from '../types';

export async function runInspection(
  imageUri: string,
  productId?: string,
): Promise<InspectionResponse> {
  const form = new FormData();

  // React Native FormData requires this specific format
  form.append('image', {
    uri: imageUri,
    type: 'image/jpeg',
    name: 'inspection.jpg',
  } as any);

  form.append('client_type', 'mobile');
  if (productId) form.append('product_id', productId);

  const { data } = await apiClient.post<InspectionResponse>('/inspections', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return data;
}

export async function getInspections(params?: {
  page?: number;
  page_size?: number;
  product_id?: string;
  decision?: string;
}): Promise<InspectionListResponse> {
  const { data } = await apiClient.get<InspectionListResponse>('/inspections', { params });
  return data;
}

export async function getProducts() {
  const { data } = await apiClient.get('/products');
  return data;
}

export async function getTodayAnalytics() {
  const { data } = await apiClient.get('/analytics/today');
  return data;
}

export async function getInspection(id: string): Promise<InspectionResponse> {
  const { data } = await apiClient.get<InspectionResponse>(`/inspections/${id}`);
  return data;
}

export async function deleteInspection(id: string): Promise<void> {
  await apiClient.delete(`/inspections/${id}`);
}

export async function uploadReferenceImage(productId: string, imageUri: string): Promise<any> {
  const form = new FormData();
  form.append('file', {
    uri: imageUri,
    type: 'image/jpeg',
    name: 'ref.jpg',
  } as any);
  const { data } = await apiClient.post(`/products/${productId}/reference-images`, form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return data;
}

export async function triggerLearnNormal(productId: string): Promise<any> {
  const { data } = await apiClient.post(`/products/${productId}/learn-normal`);
  return data;
}
