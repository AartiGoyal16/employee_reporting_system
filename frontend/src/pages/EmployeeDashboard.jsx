import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { Navbar } from '../components/Navbar';
import { WorkUpdateModal } from '../components/WorkUpdateModal';
import { updateService, reportService } from '../services/api';
import { 
  Plus, 
  Calendar, 
  Clock, 
  Tag, 
  Edit2, 
  Trash2, 
  FileText, 
  CheckCircle2, 
  AlertCircle,
  TrendingUp,
  Search,
  Filter
} from 'lucide-react';

export const EmployeeDashboard = () => {
  const [updates, setUpdates] = useState([]);
  const [loading, setLoading] = useState(true);
  const [currentReport, setCurrentReport] = useState(null);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingUpdate, setEditingUpdate] = useState(null);
  const [searchTerm, setSearchTerm] = useState('');
  const [categoryFilter, setCategoryFilter] = useState('ALL');
  const [deleteConfirmId, setDeleteConfirmId] = useState(null);

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    setLoading(true);
    try {
      const [updatesRes, reportRes] = await Promise.all([
        updateService.getUpdates(),
        reportService.getCurrentReport()
      ]);
      setUpdates(updatesRes.data);
      setCurrentReport(reportRes.data);
    } catch (err) {
      console.error("Failed to load dashboard data:", err);
    } finally {
      setLoading(false);
    }
  };

  const handleSaveUpdate = async (formData) => {
    if (editingUpdate) {
      await updateService.updateUpdate(editingUpdate.id, formData);
    } else {
      await updateService.createUpdate(formData);
    }
    await loadData();
    setEditingUpdate(null);
  };

  const handleDeleteUpdate = async (id) => {
    try {
      await updateService.deleteUpdate(id);
      setUpdates(updates.filter((u) => u.id !== id));
      setDeleteConfirmId(null);
    } catch (err) {
      console.error("Failed to delete update:", err);
    }
  };

  const openCreateModal = () => {
    setEditingUpdate(null);
    setIsModalOpen(true);
  };

  const openEditModal = (update) => {
    setEditingUpdate(update);
    setIsModalOpen(true);
  };

  // Metrics
  const totalHours = updates.reduce((sum, u) => sum + (u.hours_spent || 0), 0);
  const isReportSubmitted = currentReport?.status === 'submitted';

  const filteredUpdates = updates.filter((u) => {
    const matchesSearch = 
      u.title.toLowerCase().includes(searchTerm.toLowerCase()) ||
      u.description.toLowerCase().includes(searchTerm.toLowerCase());
    const matchesCategory = categoryFilter === 'ALL' || u.category === categoryFilter;
    return matchesSearch && matchesCategory;
  });

  const categories = ['ALL', ...new Set(updates.map((u) => u.category).filter(Boolean))];

  return (
    <div className="min-h-screen bg-slate-50 flex flex-col">
      <Navbar />

      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Welcome & Top Banner */}
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 mb-8">
          <div>
            <h1 className="text-2xl sm:text-3xl font-extrabold text-slate-900 tracking-tight">
              Employee Workspace
            </h1>
            <p className="text-sm text-slate-500 mt-1">
              Log daily work items and manage your weekly reporting deliverables.
            </p>
          </div>

          <div className="flex items-center gap-3">
            <Link
              to="/employee/weekly-report"
              className={`px-4 py-2.5 rounded-xl text-sm font-medium flex items-center gap-2 shadow-sm transition-all ${
                isReportSubmitted
                  ? 'bg-emerald-50 text-emerald-700 border border-emerald-200 hover:bg-emerald-100'
                  : 'bg-white text-blue-600 border border-blue-200 hover:bg-blue-50'
              }`}
            >
              <FileText className="w-4 h-4" />
              <span>
                {isReportSubmitted ? 'Weekly Report: Submitted' : 'Complete Weekly Report'}
              </span>
            </Link>

            <button
              onClick={openCreateModal}
              className="px-4 py-2.5 rounded-xl text-sm font-medium bg-blue-600 hover:bg-blue-700 text-white shadow-md shadow-blue-500/20 flex items-center gap-2 transition-all"
            >
              <Plus className="w-4 h-4" />
              <span>Log Daily Update</span>
            </button>
          </div>
        </div>

        {/* Overview Stats Cards */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-5 mb-8">
          <div className="bg-white p-5 rounded-2xl border border-slate-200/80 shadow-sm flex items-center gap-4">
            <div className="w-12 h-12 rounded-xl bg-blue-50 text-blue-600 flex items-center justify-center shrink-0">
              <Calendar className="w-6 h-6" />
            </div>
            <div>
              <span className="text-xs font-semibold uppercase tracking-wider text-slate-400 block">
                Work Updates Logged
              </span>
              <span className="text-2xl font-bold text-slate-900 mt-0.5 block">
                {updates.length}
              </span>
            </div>
          </div>

          <div className="bg-white p-5 rounded-2xl border border-slate-200/80 shadow-sm flex items-center gap-4">
            <div className="w-12 h-12 rounded-xl bg-indigo-50 text-indigo-600 flex items-center justify-center shrink-0">
              <Clock className="w-6 h-6" />
            </div>
            <div>
              <span className="text-xs font-semibold uppercase tracking-wider text-slate-400 block">
                Total Hours Tracked
              </span>
              <span className="text-2xl font-bold text-slate-900 mt-0.5 block">
                {totalHours.toFixed(1)} hrs
              </span>
            </div>
          </div>

          <div className="bg-white p-5 rounded-2xl border border-slate-200/80 shadow-sm flex items-center gap-4">
            <div className={`w-12 h-12 rounded-xl flex items-center justify-center shrink-0 ${
              isReportSubmitted ? 'bg-emerald-50 text-emerald-600' : 'bg-amber-50 text-amber-600'
            }`}>
              {isReportSubmitted ? (
                <CheckCircle2 className="w-6 h-6" />
              ) : (
                <AlertCircle className="w-6 h-6" />
              )}
            </div>
            <div>
              <span className="text-xs font-semibold uppercase tracking-wider text-slate-400 block">
                Current Week Status
              </span>
              <span className="text-base font-bold text-slate-900 mt-0.5 block flex items-center gap-1.5">
                <span className={`inline-block w-2 h-2 rounded-full ${
                  isReportSubmitted ? 'bg-emerald-500' : 'bg-amber-500'
                }`}></span>
                {isReportSubmitted ? 'Report Submitted (Read-Only)' : 'Draft in Progress'}
              </span>
            </div>
          </div>
        </div>

        {/* Daily Updates Section */}
        <div className="bg-white rounded-2xl border border-slate-200/80 shadow-sm overflow-hidden">
          {/* Controls bar */}
          <div className="p-5 border-b border-slate-100 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 bg-slate-50/50">
            <div>
              <h2 className="text-lg font-bold text-slate-900">Daily Work Updates</h2>
              <p className="text-xs text-slate-500">
                Log your technical accomplishments, bug fixes, code reviews, and meetings.
              </p>
            </div>

            <div className="flex flex-wrap items-center gap-3">
              {/* Search */}
              <div className="relative">
                <Search className="w-4 h-4 text-slate-400 absolute left-3 top-2.5" />
                <input
                  type="text"
                  placeholder="Search updates..."
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                  className="pl-9 pr-3 py-1.5 text-xs border border-slate-200 rounded-xl focus:ring-2 focus:ring-blue-500 focus:outline-none w-48 sm:w-56 bg-white"
                />
              </div>

              {/* Filter */}
              <div className="flex items-center gap-1 bg-white border border-slate-200 rounded-xl px-2.5 py-1 text-xs">
                <Filter className="w-3.5 h-3.5 text-slate-400" />
                <select
                  value={categoryFilter}
                  onChange={(e) => setCategoryFilter(e.target.value)}
                  className="text-xs bg-transparent focus:outline-none text-slate-700"
                >
                  {categories.map((c) => (
                    <option key={c} value={c}>
                      {c}
                    </option>
                  ))}
                </select>
              </div>
            </div>
          </div>

          {/* Updates List */}
          {loading ? (
            <div className="p-12 text-center text-slate-500">
              <div className="w-8 h-8 border-2 border-blue-600 border-t-transparent rounded-full animate-spin mx-auto mb-3"></div>
              <p className="text-sm">Loading daily updates...</p>
            </div>
          ) : filteredUpdates.length === 0 ? (
            <div className="p-12 text-center text-slate-500">
              <Calendar className="w-12 h-12 text-slate-300 mx-auto mb-3" />
              <h3 className="text-sm font-semibold text-slate-800">No work updates found</h3>
              <p className="text-xs text-slate-400 mt-1 max-w-sm mx-auto">
                {searchTerm || categoryFilter !== 'ALL'
                  ? 'No updates match your search or filter criteria.'
                  : 'Start logging your daily contributions to populate your weekly report.'}
              </p>
              <button
                onClick={openCreateModal}
                className="mt-4 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white text-xs font-medium rounded-xl transition-colors inline-flex items-center gap-1.5"
              >
                <Plus className="w-3.5 h-3.5" /> Add First Update
              </button>
            </div>
          ) : (
            <div className="divide-y divide-slate-100">
              {filteredUpdates.map((update) => (
                <div
                  key={update.id}
                  className="p-5 hover:bg-slate-50/70 transition-colors flex flex-col sm:flex-row sm:items-start justify-between gap-4 group"
                >
                  <div className="flex-1 space-y-2">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-xs font-bold text-slate-900 bg-slate-100 px-2.5 py-0.5 rounded-lg border border-slate-200">
                        {update.date}
                      </span>
                      <span className="text-xs font-semibold text-blue-700 bg-blue-50 px-2 py-0.5 rounded-lg">
                        {update.category || 'General'}
                      </span>
                      {update.hours_spent !== null && update.hours_spent !== undefined && (
                        <span className="text-xs text-slate-500 flex items-center gap-1">
                          <Clock className="w-3 h-3 text-slate-400" />
                          {update.hours_spent} hrs
                        </span>
                      )}
                    </div>

                    <h3 className="text-sm font-bold text-slate-900">{update.title}</h3>
                    <p className="text-xs text-slate-600 leading-relaxed whitespace-pre-wrap">
                      {update.description}
                    </p>
                  </div>

                  <div className="flex items-center gap-1 sm:opacity-0 group-hover:opacity-100 transition-opacity shrink-0">
                    <button
                      onClick={() => openEditModal(update)}
                      title="Edit update"
                      className="p-2 text-slate-400 hover:text-blue-600 hover:bg-blue-50 rounded-lg transition-colors"
                    >
                      <Edit2 className="w-4 h-4" />
                    </button>

                    {deleteConfirmId === update.id ? (
                      <div className="flex items-center gap-1 bg-red-50 p-1 rounded-lg border border-red-200">
                        <button
                          onClick={() => handleDeleteUpdate(update.id)}
                          className="px-2 py-1 bg-red-600 text-white rounded text-[10px] font-bold"
                        >
                          Confirm
                        </button>
                        <button
                          onClick={() => setDeleteConfirmId(null)}
                          className="px-2 py-1 text-slate-500 text-[10px]"
                        >
                          Cancel
                        </button>
                      </div>
                    ) : (
                      <button
                        onClick={() => setDeleteConfirmId(update.id)}
                        title="Delete update"
                        className="p-2 text-slate-400 hover:text-red-600 hover:bg-red-50 rounded-lg transition-colors"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </main>

      <WorkUpdateModal
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        onSave={handleSaveUpdate}
        initialData={editingUpdate}
      />
    </div>
  );
};
