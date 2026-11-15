import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider, useAuth } from './context/AuthContext';
import { ProtectedRoute } from './components/ProtectedRoute';
import { Login } from './pages/Login';
import { Signup } from './pages/Signup';
import { EmployeeDashboard } from './pages/EmployeeDashboard';
import { WeeklyReportPage } from './pages/WeeklyReportPage';
import { ReportHistoryPage } from './pages/ReportHistoryPage';
import { ManagerDashboard } from './pages/ManagerDashboard';
import { QuestionManagerPage } from './pages/QuestionManagerPage';
import { ReportDetailView } from './pages/ReportDetailView';
import { NotFound } from './pages/NotFound';

const RootRedirect = () => {
  const { isAuthenticated, role, loading } = useAuth();

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-50">
        <div className="w-8 h-8 border-3 border-blue-600 border-t-transparent rounded-full animate-spin"></div>
      </div>
    );
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  if (role === 'manager') {
    return <Navigate to="/manager" replace />;
  }

  return <Navigate to="/employee" replace />;
};

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<RootRedirect />} />
          <Route path="/login" element={<Login />} />
          <Route path="/signup" element={<Signup />} />

          {/* Employee Routes */}
          <Route
            path="/employee"
            element={
              <ProtectedRoute allowedRoles={['employee']}>
                <EmployeeDashboard />
              </ProtectedRoute>
            }
          />
          <Route
            path="/employee/weekly-report"
            element={
              <ProtectedRoute allowedRoles={['employee']}>
                <WeeklyReportPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/employee/reports"
            element={
              <ProtectedRoute allowedRoles={['employee']}>
                <ReportHistoryPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/reports/:id"
            element={
              <ProtectedRoute allowedRoles={['employee', 'manager']}>
                <ReportDetailView />
              </ProtectedRoute>
            }
          />

          {/* Manager Routes */}
          <Route
            path="/manager"
            element={
              <ProtectedRoute allowedRoles={['manager']}>
                <ManagerDashboard />
              </ProtectedRoute>
            }
          />
          <Route
            path="/manager/questions"
            element={
              <ProtectedRoute allowedRoles={['manager']}>
                <QuestionManagerPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/manager/reports/:id"
            element={
              <ProtectedRoute allowedRoles={['manager']}>
                <ReportDetailView />
              </ProtectedRoute>
            }
          />

          {/* Fallback */}
          <Route path="*" element={<NotFound />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}
