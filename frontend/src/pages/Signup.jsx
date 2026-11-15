import React, { useState, useEffect } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { authService } from '../services/api';
import {
  ClipboardList,
  UserPlus,
  AlertCircle,
  Eye,
  EyeOff,
  User,
  Mail,
  Lock,
  Building2,
  Users,
  CheckCircle2,
  ArrowRight,
  ChevronDown
} from 'lucide-react';

const DEPARTMENTS = [
  'Engineering Core',
  'Product & UX',
  'Quality Assurance',
  'DevOps & Infrastructure',
  'Data & Analytics',
  'Marketing & Growth',
  'Sales & Partnerships',
  'Customer Success',
  'Finance & Operations',
  'Human Resources',
  'Other',
];

export const Signup = () => {
  const navigate = useNavigate();
  const { register, isAuthenticated, role } = useAuth();

  const [formData, setFormData] = useState({
    name: '',
    email: '',
    password: '',
    confirmPassword: '',
    role: 'employee',
    department: 'Engineering Core',
    manager_id: '',
  });
  const [errors, setErrors] = useState({});
  const [serverError, setServerError] = useState('');
  const [loading, setLoading] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);
  const [managers, setManagers] = useState([]);
  const [managersLoading, setManagersLoading] = useState(false);
  const [success, setSuccess] = useState(false);

  // Redirect if already authenticated
  useEffect(() => {
    if (isAuthenticated) {
      navigate(role === 'manager' ? '/manager' : '/employee', { replace: true });
    }
  }, [isAuthenticated, role, navigate]);

  // Load managers for the dropdown
  useEffect(() => {
    const fetchManagers = async () => {
      setManagersLoading(true);
      try {
        const res = await authService.getManagers();
        setManagers(res.data);
      } catch (err) {
        console.error('Could not fetch managers:', err);
      } finally {
        setManagersLoading(false);
      }
    };
    fetchManagers();
  }, []);

  const handleChange = (e) => {
    const { name, value } = e.target;
    setFormData((prev) => ({ ...prev, [name]: value }));
    if (errors[name]) setErrors((prev) => ({ ...prev, [name]: '' }));
    setServerError('');
  };

  const validate = () => {
    const newErrors = {};
    if (!formData.name.trim() || formData.name.trim().length < 2) {
      newErrors.name = 'Full name must be at least 2 characters.';
    }
    if (!formData.email.trim()) {
      newErrors.email = 'Email address is required.';
    } else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(formData.email)) {
      newErrors.email = 'Please enter a valid email address.';
    }
    if (!formData.password) {
      newErrors.password = 'Password is required.';
    } else if (formData.password.length < 6) {
      newErrors.password = 'Password must be at least 6 characters.';
    }
    if (formData.password !== formData.confirmPassword) {
      newErrors.confirmPassword = 'Passwords do not match.';
    }
    if (!formData.department) {
      newErrors.department = 'Please select a department.';
    }
    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!validate()) return;

    setLoading(true);
    setServerError('');

    const payload = {
      name: formData.name.trim(),
      email: formData.email.trim().toLowerCase(),
      password: formData.password,
      role: formData.role,
      department: formData.department,
      ...(formData.role === 'employee' && formData.manager_id
        ? { manager_id: formData.manager_id }
        : {}),
    };

    try {
      setSuccess(true);
      await new Promise((r) => setTimeout(r, 500));
      const user = await register(payload);
      navigate(user.role === 'manager' ? '/manager' : '/employee', { replace: true });
    } catch (err) {
      console.error(err);
      setSuccess(false);
      setServerError(
        err.response?.data?.detail || 'Registration failed. Please try again.'
      );
    } finally {
      setLoading(false);
    }
  };

  // Password strength meter
  const passwordStrength = (() => {
    const p = formData.password;
    if (!p) return { level: 0, label: '', color: '' };
    let score = 0;
    if (p.length >= 6) score++;
    if (p.length >= 10) score++;
    if (/[A-Z]/.test(p)) score++;
    if (/[0-9]/.test(p)) score++;
    if (/[^A-Za-z0-9]/.test(p)) score++;
    if (score <= 1) return { level: 1, label: 'Weak', color: 'bg-red-500' };
    if (score <= 2) return { level: 2, label: 'Fair', color: 'bg-amber-500' };
    if (score <= 3) return { level: 3, label: 'Good', color: 'bg-blue-500' };
    return { level: 4, label: 'Strong', color: 'bg-emerald-500' };
  })();

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-indigo-950 to-slate-900 flex flex-col justify-center py-12 sm:px-6 lg:px-8 relative overflow-hidden">
      {/* Ambient glows */}
      <div className="absolute top-0 left-1/4 w-96 h-96 bg-indigo-500/8 rounded-full blur-3xl pointer-events-none" />
      <div className="absolute bottom-0 right-1/4 w-96 h-96 bg-blue-500/8 rounded-full blur-3xl pointer-events-none" />

      {/* Header */}
      <div className="sm:mx-auto sm:w-full sm:max-w-md text-center z-10 mb-6">
        <div className="inline-flex items-center justify-center w-14 h-14 rounded-2xl bg-gradient-to-tr from-indigo-500 to-blue-600 text-white shadow-xl shadow-indigo-500/30 mb-4">
          <ClipboardList className="w-7 h-7" />
        </div>
        <h2 className="text-3xl font-extrabold text-white tracking-tight">Create Your Account</h2>
        <p className="mt-2 text-sm text-slate-300">
          Join the Employee Reporting System · Role-based access included
        </p>
      </div>

      {/* Form Card */}
      <div className="sm:mx-auto sm:w-full sm:max-w-lg z-10 px-4 sm:px-0">
        <div className="bg-white/95 backdrop-blur-xl shadow-2xl rounded-2xl border border-white/20 overflow-hidden">
          {/* Role tabs */}
          <div className="flex border-b border-slate-200">
            {[
              { key: 'employee', label: '👤 Register as Employee' },
              { key: 'manager', label: '🏢 Register as Manager' },
            ].map(({ key, label }) => (
              <button
                key={key}
                type="button"
                onClick={() => {
                  setFormData((prev) => ({ ...prev, role: key, manager_id: '' }));
                  setErrors((prev) => ({ ...prev, manager_id: '' }));
                }}
                className={`flex-1 py-3 text-xs sm:text-sm font-semibold tracking-wide transition-colors ${
                  formData.role === key
                    ? key === 'manager'
                      ? 'bg-purple-50 text-purple-700 border-b-2 border-purple-600'
                      : 'bg-blue-50 text-blue-700 border-b-2 border-blue-600'
                    : 'text-slate-500 hover:text-slate-700 hover:bg-slate-50'
                }`}
              >
                {label}
              </button>
            ))}
          </div>

          <form onSubmit={handleSubmit} className="p-6 space-y-4">
            {/* Server error */}
            {serverError && (
              <div className="p-3.5 bg-red-50 border border-red-200 rounded-xl flex items-start gap-2.5 text-sm text-red-700">
                <AlertCircle className="w-5 h-5 mt-0.5 shrink-0 text-red-500" />
                <span>{serverError}</span>
              </div>
            )}
            {success && (
              <div className="p-3.5 bg-emerald-50 border border-emerald-200 rounded-xl flex items-center gap-2.5 text-sm text-emerald-700">
                <CheckCircle2 className="w-5 h-5 text-emerald-500 shrink-0" />
                <span>Account created! Redirecting to your dashboard…</span>
              </div>
            )}

            {/* Name */}
            <div>
              <label className="block text-xs font-semibold uppercase tracking-wider text-slate-600 mb-1.5">
                Full Name
              </label>
              <div className="relative">
                <User className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400 pointer-events-none" />
                <input
                  type="text"
                  name="name"
                  value={formData.name}
                  onChange={handleChange}
                  placeholder="Jane Smith"
                  required
                  className={`w-full pl-9 pr-3.5 py-2.5 text-sm border rounded-xl focus:ring-2 focus:ring-indigo-500 focus:outline-none transition-colors ${errors.name ? 'border-red-400 bg-red-50/40' : 'border-slate-300'}`}
                />
              </div>
              {errors.name && <p className="mt-1 text-xs text-red-600 flex items-center gap-1"><AlertCircle className="w-3 h-3" />{errors.name}</p>}
            </div>

            {/* Email */}
            <div>
              <label className="block text-xs font-semibold uppercase tracking-wider text-slate-600 mb-1.5">
                Work Email
              </label>
              <div className="relative">
                <Mail className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400 pointer-events-none" />
                <input
                  type="email"
                  name="email"
                  value={formData.email}
                  onChange={handleChange}
                  placeholder="jane@company.com"
                  required
                  className={`w-full pl-9 pr-3.5 py-2.5 text-sm border rounded-xl focus:ring-2 focus:ring-indigo-500 focus:outline-none transition-colors ${errors.email ? 'border-red-400 bg-red-50/40' : 'border-slate-300'}`}
                />
              </div>
              {errors.email && <p className="mt-1 text-xs text-red-600 flex items-center gap-1"><AlertCircle className="w-3 h-3" />{errors.email}</p>}
            </div>

            {/* Department */}
            <div>
              <label className="block text-xs font-semibold uppercase tracking-wider text-slate-600 mb-1.5 flex items-center gap-1">
                <Building2 className="w-3.5 h-3.5 text-slate-400" /> Department
              </label>
              <div className="relative">
                <select
                  name="department"
                  value={formData.department}
                  onChange={handleChange}
                  className="w-full px-3.5 py-2.5 text-sm border border-slate-300 rounded-xl focus:ring-2 focus:ring-indigo-500 focus:outline-none bg-white appearance-none pr-10"
                >
                  {DEPARTMENTS.map((d) => (
                    <option key={d} value={d}>{d}</option>
                  ))}
                </select>
                <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400 pointer-events-none" />
              </div>
            </div>

            {/* Manager dropdown — only for employees */}
            {formData.role === 'employee' && (
              <div>
                <label className="block text-xs font-semibold uppercase tracking-wider text-slate-600 mb-1.5 flex items-center gap-1.5">
                  <Users className="w-3.5 h-3.5 text-slate-400" />
                  Reports To
                  <span className="normal-case font-normal text-slate-400 ml-1">(optional)</span>
                </label>
                <div className="relative">
                  <select
                    name="manager_id"
                    value={formData.manager_id}
                    onChange={handleChange}
                    disabled={managersLoading}
                    className="w-full px-3.5 py-2.5 text-sm border border-slate-300 rounded-xl focus:ring-2 focus:ring-indigo-500 focus:outline-none bg-white appearance-none pr-10 disabled:opacity-60"
                  >
                    <option value="">
                      {managersLoading ? 'Loading managers…' : '— No manager selected —'}
                    </option>
                    {managers.map((m) => (
                      <option key={m.id} value={m.id}>
                        {m.name} · {m.department}
                      </option>
                    ))}
                  </select>
                  <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400 pointer-events-none" />
                </div>
                <p className="mt-1 text-[11px] text-slate-400">
                  Your manager will be able to view your submitted weekly reports.
                </p>
              </div>
            )}

            {/* Password */}
            <div>
              <label className="block text-xs font-semibold uppercase tracking-wider text-slate-600 mb-1.5">
                Password
              </label>
              <div className="relative">
                <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400 pointer-events-none" />
                <input
                  type={showPassword ? 'text' : 'password'}
                  name="password"
                  value={formData.password}
                  onChange={handleChange}
                  placeholder="Min. 6 characters"
                  required
                  className={`w-full pl-9 pr-10 py-2.5 text-sm border rounded-xl focus:ring-2 focus:ring-indigo-500 focus:outline-none transition-colors ${errors.password ? 'border-red-400 bg-red-50/40' : 'border-slate-300'}`}
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600"
                >
                  {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
              {/* Strength meter */}
              {formData.password && (
                <div className="mt-2">
                  <div className="flex gap-1 mb-1">
                    {[1, 2, 3, 4].map((i) => (
                      <div
                        key={i}
                        className={`h-1 flex-1 rounded-full transition-colors duration-300 ${i <= passwordStrength.level ? passwordStrength.color : 'bg-slate-200'}`}
                      />
                    ))}
                  </div>
                  <span className={`text-[11px] font-medium ${
                    passwordStrength.level <= 1 ? 'text-red-600' :
                    passwordStrength.level === 2 ? 'text-amber-600' :
                    passwordStrength.level === 3 ? 'text-blue-600' : 'text-emerald-600'
                  }`}>
                    {passwordStrength.label} password
                  </span>
                </div>
              )}
              {errors.password && <p className="mt-1 text-xs text-red-600 flex items-center gap-1"><AlertCircle className="w-3 h-3" />{errors.password}</p>}
            </div>

            {/* Confirm Password */}
            <div>
              <label className="block text-xs font-semibold uppercase tracking-wider text-slate-600 mb-1.5">
                Confirm Password
              </label>
              <div className="relative">
                <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400 pointer-events-none" />
                <input
                  type={showConfirm ? 'text' : 'password'}
                  name="confirmPassword"
                  value={formData.confirmPassword}
                  onChange={handleChange}
                  placeholder="Re-enter your password"
                  required
                  className={`w-full pl-9 pr-10 py-2.5 text-sm border rounded-xl focus:ring-2 focus:ring-indigo-500 focus:outline-none transition-colors ${errors.confirmPassword ? 'border-red-400 bg-red-50/40' : 'border-slate-300'}`}
                />
                <button
                  type="button"
                  onClick={() => setShowConfirm(!showConfirm)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600"
                >
                  {showConfirm ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
              {errors.confirmPassword && <p className="mt-1 text-xs text-red-600 flex items-center gap-1"><AlertCircle className="w-3 h-3" />{errors.confirmPassword}</p>}
              {formData.confirmPassword && formData.password === formData.confirmPassword && (
                <p className="mt-1 text-xs text-emerald-600 flex items-center gap-1">
                  <CheckCircle2 className="w-3 h-3" /> Passwords match
                </p>
              )}
            </div>

            {/* Submit */}
            <button
              type="submit"
              disabled={loading || success}
              className="w-full py-3 mt-2 bg-gradient-to-r from-indigo-600 to-blue-600 hover:from-indigo-700 hover:to-blue-700 text-white font-semibold rounded-xl shadow-lg shadow-indigo-500/25 flex items-center justify-center gap-2 transition-all disabled:opacity-60 disabled:cursor-not-allowed"
            >
              {loading ? (
                <>
                  <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                  Creating account…
                </>
              ) : success ? (
                <>
                  <CheckCircle2 className="w-4 h-4" /> Redirecting…
                </>
              ) : (
                <>
                  <UserPlus className="w-4 h-4" />
                  Create Account &amp; Sign In
                  <ArrowRight className="w-4 h-4 ml-1" />
                </>
              )}
            </button>

            <p className="text-center text-sm text-slate-500 pt-1">
              Already have an account?{' '}
              <Link to="/login" className="font-semibold text-indigo-600 hover:text-indigo-700 hover:underline">
                Sign in here →
              </Link>
            </p>
          </form>
        </div>

        <p className="mt-5 text-center text-xs text-slate-400">
          Role-Based Access Control · FastAPI · MongoDB · Google Gemini AI
        </p>
      </div>
    </div>
  );
};
