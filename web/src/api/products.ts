import { readShared } from './reads';
import apiClient from './client';
import type { Product, ProductCreate, ProductUpdate, ReferenceImage } from '../types';

export interface TrainedProfile {
  id: string;
  label: string;
  dataset: string;
  category: string;
  metrics: { f2: number; precision: number; recall: number; accuracy: number; false_reject_rate?: number | null };
}

export interface LearnNormalStatus {
  product_id: string;
  model_status: string;
  reference_image_count: number;
  min_images_required: number;
  can_start_training: boolean;
  status?: string;
  message?: string;
  estimated_seconds?: number;
}

export async function getTrainedProfiles(): Promise<TrainedProfile[]> {
  return readShared('/products/trained-profiles', async () => {
    const { data } = await apiClient.get<TrainedProfile[]>('/products/trained-profiles');
    return data;
  });
}

export async function assignModelProfile(id: string, profileId: string): Promise<Product> {
  const { data } = await apiClient.put<Product>(`/products/${id}/model-profile`, { profile_id: profileId });
  return data;
}

export async function startLearnNormal(productId: string): Promise<LearnNormalStatus> {
  const { data } = await apiClient.post<LearnNormalStatus>(`/products/${productId}/learn-normal`);
  return data;
}

export async function getLearnNormalStatus(productId: string): Promise<LearnNormalStatus> {
  return readShared(`/products/${productId}/learn-normal/status`, async () => {
    const { data } = await apiClient.get<LearnNormalStatus>(`/products/${productId}/learn-normal/status`);
    return data;
  });
}

export async function getProducts(): Promise<Product[]> {
  return readShared('/products', async () => {
    const { data } = await apiClient.get<Product[]>('/products');
    return data;
  }, 5000);
}

export async function createProduct(body: ProductCreate): Promise<Product> {
  const { data } = await apiClient.post<Product>('/products', body);
  return data;
}

export async function getProduct(id: string): Promise<Product> {
  return readShared(`/products/${id}`, async () => {
    const { data } = await apiClient.get<Product>(`/products/${id}`);
    return data;
  });
}

export async function updateProduct(id: string, body: ProductUpdate): Promise<Product> {
  const { data } = await apiClient.patch<Product>(`/products/${id}`, body);
  return data;
}

export async function deleteProduct(id: string): Promise<void> {
  await apiClient.delete(`/products/${id}`);
}

export async function updateThreshold(id: string, threshold: number): Promise<Product> {
  const { data } = await apiClient.put<Product>(`/products/${id}/threshold`, { threshold });
  return data;
}

export async function uploadReferenceImage(
  productId: string,
  file: File
): Promise<ReferenceImage> {
  const form = new FormData();
  form.append('file', file);
  const { data } = await apiClient.post<ReferenceImage>(
    `/products/${productId}/reference-images`,
    form,
    {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 120000,
    }
  );
  return data;
}

export async function uploadReferenceImagesZip(
  productId: string,
  file: File
): Promise<ReferenceImage[]> {
  const form = new FormData();
  form.append('file', file);
  const { data } = await apiClient.post<ReferenceImage[]>(
    `/products/${productId}/reference-images/zip`,
    form,
    {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 300000,
    }
  );
  return data;
}

export async function getReferenceImages(productId: string): Promise<ReferenceImage[]> {
  return readShared(`/products/${productId}/reference-images`, async () => {
    const { data } = await apiClient.get<ReferenceImage[]>(
    `/products/${productId}/reference-images`
  );
    return data;
  });
}

export async function deleteReferenceImage(
  productId: string,
  imageId: string
): Promise<void> {
  await apiClient.delete(`/products/${productId}/reference-images/${imageId}`);
}
