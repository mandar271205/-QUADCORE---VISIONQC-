import apiClient from './client';
import type { Product, ProductCreate, ProductUpdate, ReferenceImage } from '../types';

export async function getProducts(): Promise<Product[]> {
  const { data } = await apiClient.get<Product[]>('/products');
  return data;
}

export async function createProduct(body: ProductCreate): Promise<Product> {
  const { data } = await apiClient.post<Product>('/products', body);
  return data;
}

export async function getProduct(id: string): Promise<Product> {
  const { data } = await apiClient.get<Product>(`/products/${id}`);
  return data;
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
    { headers: { 'Content-Type': 'multipart/form-data' } }
  );
  return data;
}

export async function getReferenceImages(productId: string): Promise<ReferenceImage[]> {
  const { data } = await apiClient.get<ReferenceImage[]>(
    `/products/${productId}/reference-images`
  );
  return data;
}

export async function deleteReferenceImage(
  productId: string,
  imageId: string
): Promise<void> {
  await apiClient.delete(`/products/${productId}/reference-images/${imageId}`);
}
