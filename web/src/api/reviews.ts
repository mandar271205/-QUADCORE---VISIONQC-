import { apiClient } from './client';
import type { PendingReviewListResponse, PendingReviewItem } from '../types';

export const reviewsApi = {
  getPendingReviews: async (page = 1, pageSize = 20, status = 'pending'): Promise<PendingReviewListResponse> => {
    const { data } = await apiClient.get<PendingReviewListResponse>('/reviews', {
      params: { page, page_size: pageSize, status },
    });
    return data;
  },

  getReviewCount: async (): Promise<{ pending: number }> => {
    const { data } = await apiClient.get<{ pending: number }>('/reviews/count');
    return data;
  },

  submitReviewDecision: async (inspectionId: string, action: 'accept' | 'reject', note?: string): Promise<PendingReviewItem> => {
    const { data } = await apiClient.post<PendingReviewItem>(`/reviews/${inspectionId}/decision`, { action, note });
    return data;
  },
};
