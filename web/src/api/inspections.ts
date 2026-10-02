import apiClient from './client';
import type { InspectionResponse, InspectionListResponse } from '../types';

export async function runInspection(
  image: File,
  productId?: string,
  clientType: 'web' | 'mobile' = 'web'
): Promise<InspectionResponse> {
  const form = new FormData();
  form.append('image', image);
  if (productId) form.append('product_id', productId);
  form.append('client_type', clientType);

  const { data } = await apiClient.post<InspectionResponse>('/inspections', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 60000,
  });
  return data;
}

export async function getInspections(params?: {
  page?: number;
  page_size?: number;
  product_id?: string;
  decision?: string;
  date_from?: string;
  date_to?: string;
}): Promise<InspectionListResponse> {
  const { data } = await apiClient.get<InspectionListResponse>('/inspections', { params });
  return data;
}

export async function getInspection(id: string): Promise<InspectionResponse> {
  const { data } = await apiClient.get<InspectionResponse>(`/inspections/${id}`);
  return data;
}

export async function deleteInspection(id: string): Promise<void> {
  await apiClient.delete(`/inspections/${id}`);
}
