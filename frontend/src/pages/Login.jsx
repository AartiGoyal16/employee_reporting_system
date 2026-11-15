import React, { useState, useEffect } from 'react';
import { useNavigate, useLocation, Link } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { authService } from '../services/api';
import { 
  ClipboardList, 
  LogIn, 
  UserCheck, 
  AlertCircle, 
  Sparkles, 
  ShieldCheck,
  ChevronRight
} from 'lucide-react';

export const Login = () => {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [demoUsers, setDemoUsers] = useState([]);

  const { login, isAuthenticated, role } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  useEffect(() => {
    if (isAuthenticated) {
      if (role === 'manager') {
        navigate('/manager', { replace: true });
      } else {
        navigate('/employee', { replace: true });
      }
    }
  }, [isAuthenticated, role, navigate]);

  useEffect(() => {
    // Fetch demo users for 1-click evaluation (available in development mode)
    authService.getDemoUsers()
      .then((res) => setDemoUsers(res.data || []))
      .catch(() => setDemoUsers([]));
  }, []);

  const handleLogin = async (e) => {
    e.preventDefault();
    if (!email || !password) {
      setError('Please fill in both email and password.');
      return;
    }

    setLoading(true);
    setError('');
    try {
      const user = await login(email, password);
      if (user.role === 'manager') {
        navigate('/manager');
      } else {
        navigate('/employee');
      }
    } catch (err) {
      console.error(err);
      setError(err.response?.data?.detail || 'Invalid email or password.');
    } finally {
      setLoading(false);
    }
  };

  const handleQuickLogin = async (demoUser) => {
    setEmail(demoUser.email);
    setPassword(demoUser.password);
    setLoading(true);
    setError('');
    try {
      const user = await login(demoUser.email, demoUser.password);
      if (user.role === 'manager') {
        navigate('/manager');
      } else {
        navigate('/employee');
      }
    } catch (err) {
      console.error(err);
      setError(err.response?.data?.detail || 'Failed to authenticate demo user.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-slate-800 to-indigo-950 flex flex-col justify-center py-12 sm:px-6 lg:px-8 relative overflow-hidden">
      {/* Background ambient lighting */}
      <div className="absolute top-0 right-1/4 w-96 h-96 bg-blue-500/10 rounded-full blur-3xl pointer-events-none"></div>
      <div className="absolute bottom-0 left-1/4 w-96 h-96 bg-indigo-500/10 rounded-full blur-3xl pointer-events-none"></div>

      <div className="sm:mx-auto sm:w-full sm:max-w-md text-center z-10">
        <div className="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-gradient-to-tr from-blue-500 to-indigo-600 text-white shadow-xl shadow-blue-500/30 mb-4">
          <ClipboardList className="w-8 h-8" />
        </div>
        <h2 className="text-3xl font-extrabold text-white tracking-tight">
          Employee Reporting System
        </h2>
        <p className="mt-2 text-sm text-slate-300">
          Daily Work Updates & AI-Powered Weekly Syntheses
        </p>
      </div>

      <div className="mt-8 sm:mx-auto sm:w-full sm:max-w-md z-10 px-4 sm:px-0">
        <div className="bg-white/95 backdrop-blur-xl py-8 px-6 shadow-2xl rounded-2xl border border-white/20 sm:px-10">
          {error && (
            <div className="mb-5 p-3.5 bg-red-50 border border-red-200 rounded-xl flex items-start gap-2.5 text-sm text-red-700">
              <AlertCircle className="w-5 h-5 mt-0.5 shrink-0" />
              <span>{error}</span>
            </div>
          )}

          <form className="space-y-4" onSubmit={handleLogin}>
            <div>
              <label className="block text-xs font-semibold uppercase tracking-wider text-slate-600 mb-1">
                Work Email
              </label>
              <input
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="w-full px-3.5 py-2.5 text-sm border border-slate-300 rounded-xl focus:ring-2 focus:ring-blue-500 focus:outline-none"
                placeholder="name@company.com"
              />
            </div>

            <div>
              <label className="block text-xs font-semibold uppercase tracking-wider text-slate-600 mb-1">
                Password
              </label>
              <input
                type="password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full px-3.5 py-2.5 text-sm border border-slate-300 rounded-xl focus:ring-2 focus:ring-blue-500 focus:outline-none"
                placeholder="••••••••"
              />
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full py-2.5 px-4 bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-700 hover:to-indigo-700 text-white font-medium rounded-xl shadow-md shadow-blue-500/25 flex items-center justify-center gap-2 transition-all disabled:opacity-50"
            >
              <LogIn className="w-4 h-4" />
              {loading ? 'Signing in...' : 'Sign In'}
            </button>

            <div className="pt-2 text-center">
              <span className="text-xs text-slate-500">Don't have an account? </span>
              <Link to="/signup" className="text-xs font-semibold text-blue-600 hover:text-blue-700 hover:underline">
                Create an account &rarr;
              </Link>
            </div>
          </form>

          {/* Quick Demo Switcher Section (visible in development only) */}
          {demoUsers && demoUsers.length > 0 && (
            <div className="mt-8 pt-6 border-t border-slate-200">
              <div className="flex items-center justify-between mb-3">
                <span className="text-xs font-bold uppercase tracking-wider text-slate-500 flex items-center gap-1.5">
                  <Sparkles className="w-3.5 h-3.5 text-amber-500" />
                  Quick 1-Click Demo Logins
                </span>
                <span className="text-[10px] bg-slate-100 text-slate-600 px-2 py-0.5 rounded-full font-medium">
                  No typing required
                </span>
              </div>

              <div className="space-y-2">
                {demoUsers.map((u) => {
                  const isMgr = u.role === 'manager';
                  return (
                    <button
                      key={u.email}
                      type="button"
                      onClick={() => handleQuickLogin(u)}
                      className="w-full p-2.5 text-left rounded-xl border border-slate-200 hover:border-blue-400 hover:bg-blue-50/50 flex items-center justify-between group transition-all"
                    >
                      <div className="flex items-center gap-2.5">
                        <div className={`w-8 h-8 rounded-lg flex items-center justify-center text-xs font-bold ${
                          isMgr 
                            ? 'bg-purple-100 text-purple-700' 
                            : 'bg-blue-100 text-blue-700'
                        }`}>
                          {u.name.charAt(0)}
                        </div>
                        <div>
                          <div className="text-xs font-semibold text-slate-800 flex items-center gap-1.5">
                            <span>{u.name}</span>
                            <span className={`text-[10px] font-semibold px-1.5 py-0.2 rounded uppercase ${
                              isMgr 
                                ? 'bg-purple-50 text-purple-700' 
                                : 'bg-blue-50 text-blue-700'
                            }`}>
                              {u.role}
                            </span>
                          </div>
                          <div className="text-[11px] text-slate-500">{u.description}</div>
                        </div>
                      </div>
                      <ChevronRight className="w-4 h-4 text-slate-400 group-hover:text-blue-600 group-hover:translate-x-0.5 transition-all" />
                    </button>
                  );
                })}
              </div>
            </div>
          )}
        </div>

        <div className="mt-6 text-center text-xs text-slate-400">
          <span>Role-Based Access Control • MongoDB • FastAPI • Google Gemini AI</span>
        </div>
      </div>
    </div>
  );
};
