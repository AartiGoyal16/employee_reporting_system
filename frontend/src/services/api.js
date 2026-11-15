import axios from 'axios';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api/v1';

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Attach JWT token to requests
api.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

// Global response interceptor for auth expiration
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response && error.response.status === 401) {
      // Clear token if expired/invalid
      if (!window.location.pathname.includes('/login')) {
        localStorage.removeItem('token');
        localStorage.removeItem('user');
        window.location.href = '/login?expired=1';
      }
    }
    return Promise.reject(error);
  }
);

// Auth Services
export const authService = {
  login: (email, password) => api.post('/auth/login', { email, password }),
  register: (data) => api.post('/auth/register', data),
  getManagers: () => api.get('/auth/managers'),
  getMe: () => api.get('/auth/me'),
  getDemoUsers: () => api.get('/auth/demo-users'),
};

// Work Updates Services
export const updateService = {
  getUpdates: (params) => api.get('/updates', { params }),
  createUpdate: (data) => api.post('/updates', data),
  getUpdateById: (id) => api.get(`/updates/${id}`),
  updateUpdate: (id, data) => api.put(`/updates/${id}`, data),
  deleteUpdate: (id) => api.delete(`/updates/${id}`),
};

// Weekly Questions Services
export const questionService = {
  getQuestions: (params) => api.get('/questions', { params }),
  createQuestion: (data) => api.post('/questions', data),
  updateQuestion: (id, data) => api.put(`/questions/${id}`, data),
  toggleQuestion: (id) => api.patch(`/questions/${id}/toggle`),
  deleteQuestion: (id) => api.delete(`/questions/${id}`),
};

// Weekly Reports Services
export const reportService = {
  getCurrentReport: () => api.get('/reports/current'),
  getReportHistory: () => api.get('/reports'),
  getReportById: (id) => api.get(`/reports/${id}`),
  saveDraft: (data) => api.post('/reports/draft', data),
  submitReport: (id, data) => api.post(`/reports/${id}/submit`, data),
  downloadPdf: async (id, filename) => {
    const response = await api.get(`/reports/${id}/pdf`, { responseType: 'blob' });
    const blob = new Blob([response.data], { type: 'application/pdf' });
    const url = window.URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.setAttribute('download', filename || `Weekly_Report_${id}.pdf`);
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.URL.revokeObjectURL(url);
  },
};

// Manager Services
export const managerService = {
  getEmployees: () => api.get('/manager/employees'),
  getReports: (params) => api.get('/manager/reports', { params }),
  getReportDetail: (id) => api.get(`/manager/reports/${id}`),
};

export default api;
