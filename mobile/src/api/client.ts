import axios from 'axios';
import { Platform } from 'react-native';

// On Android emulator, localhost is 10.0.2.2
// On physical device, use your machine's local IP
const getBaseUrl = () => {
  if (process.env.EXPO_PUBLIC_API_URL) return process.env.EXPO_PUBLIC_API_URL;
  const port = process.env.EXPO_PUBLIC_API_PORT || '8000';
  if (Platform.OS === 'android') return `http://10.0.2.2:${port}/api/v1`;
  return `http://localhost:${port}/api/v1`;
};

export const apiClient = axios.create({
  baseURL: getBaseUrl(),
  timeout: 60000,
});

apiClient.interceptors.response.use(
  r => r,
  err => {
    const message = err.response?.data?.detail || err.message || 'Request failed.';
    return Promise.reject(new Error(message));
  }
);
