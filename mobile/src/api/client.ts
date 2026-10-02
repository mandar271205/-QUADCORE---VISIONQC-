import axios from 'axios';
import { Platform } from 'react-native';

// On Android emulator, localhost is 10.0.2.2
// On physical device, use your machine's local IP
const getBaseUrl = () => {
  if (process.env.EXPO_PUBLIC_API_URL) return process.env.EXPO_PUBLIC_API_URL;
  if (Platform.OS === 'android') return 'http://10.0.2.2:8000/api/v1';
  return 'http://localhost:8000/api/v1';
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
