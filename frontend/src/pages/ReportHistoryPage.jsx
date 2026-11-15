import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { Navbar } from '../components/Navbar';
import { reportService } from '../services/api';
import {
  Calendar,
  Clock,
  Download,
  FileText,
  CheckCircle2,
  AlertCircle,
  ChevronRight,
  Eye,
  Sparkles,
  ArrowLeft,
  Plus
} from 'lucide-react';

export const ReportHistoryPage = () => {
  const [reports, setReports] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [downloadingId, setDownloadingId] = useState(null);

  useEffect(() => {
    loadReports();
  }, []);

  const loadReports = async () => {
    setLoading(true);
    setError('');
    try {
      const res = await reportService.getReportHistory();
      setReports(res.data);
    } catch (err) {
      console.error('Failed to load report history:', err);
      setError('Could not load weekly report history. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  const handleDownloadPdf = async (e, report) => {
    e.stopPropagation();
    e.preventDefault();
    setDownloadingId(report.id);
    try {
      const filename = `Weekly_Report_${report.week_start_date}_${(report.user_name || 'Employee').replace(/\s+/g, '_')}.pdf`;
      await reportService.downloadPdf(report.id, filename);
    } catch (err) {
      console.error('Download PDF failed:', err);
      alert('Could not generate PDF. Please try again.');
    } finally {
      setDownloadingId(null);
    }
  };

  const submittedCount = reports.filter((r) => r.status === 'submitted').length;
  const draftCount = reports.filter((r) => r.status === 'draft').length;

  return (
    <div className="min-h-screen bg-slate-50 flex flex-col">
      <Navbar />

      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Header Navigation */}
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 mb-8">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <Link
                to="/employee"
                className="text-xs font-semibold text-slate-500 hover:text-slate-800 flex items-center gap-1 transition-colors"
              >
                <ArrowLeft className="w-3.5 h-3.5" /> Back to Dashboard
              </Link>
            </div>
            <h1 className="text-2xl sm:text-3xl font-extrabold text-slate-900 tracking-tight flex items-center gap-2.5">
              <FileText className="w-7 h-7 text-blue-600" />
              Weekly Report History
            </h1>
            <p className="text-sm text-slate-500 mt-1">
              Track past submissions, review AI executive summaries, and download signed PDF reports.
            </p>
          </div>

          <div className="flex items-center gap-3">
            <Link
              to="/employee/weekly-report"
              className="px-4 py-2.5 rounded-xl text-sm font-semibold bg-blue-600 hover:bg-blue-700 text-white shadow-md shadow-blue-500/20 flex items-center gap-2 transition-all"
            >
              <Plus className="w-4 h-4" /> Current Week Report
            </Link>
          </div>
        </div>

        {/* Stats Summary Pills */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-6">
          <div className="bg-white p-5 rounded-2xl border border-slate-200/80 shadow-sm flex items-center justify-between">
            <div>
              <span className="text-xs font-bold uppercase tracking-wider text-slate-400">Total Reports</span>
              <p className="text-2xl font-black text-slate-900 mt-0.5">{reports.length}</p>
            </div>
            <div className="w-11 h-11 rounded-xl bg-blue-50 text-blue-600 flex items-center justify-center">
              <FileText className="w-5 h-5" />
            </div>
          </div>

          <div className="bg-white p-5 rounded-2xl border border-slate-200/80 shadow-sm flex items-center justify-between">
            <div>
              <span className="text-xs font-bold uppercase tracking-wider text-slate-400">Submitted</span>
              <p className="text-2xl font-black text-emerald-600 mt-0.5">{submittedCount}</p>
            </div>
            <div className="w-11 h-11 rounded-xl bg-emerald-50 text-emerald-600 flex items-center justify-center">
              <CheckCircle2 className="w-5 h-5" />
            </div>
          </div>

          <div className="bg-white p-5 rounded-2xl border border-slate-200/80 shadow-sm flex items-center justify-between">
            <div>
              <span className="text-xs font-bold uppercase tracking-wider text-slate-400">In Draft</span>
              <p className="text-2xl font-black text-amber-600 mt-0.5">{draftCount}</p>
            </div>
            <div className="w-11 h-11 rounded-xl bg-amber-50 text-amber-600 flex items-center justify-center">
              <Clock className="w-5 h-5" />
            </div>
          </div>
        </div>

        {/* Error Alert */}
        {error && (
          <div className="p-4 bg-red-50 border border-red-200 rounded-2xl text-sm text-red-700 flex items-center gap-3 mb-6">
            <AlertCircle className="w-5 h-5 shrink-0 text-red-500" />
            <span>{error}</span>
          </div>
        )}

        {/* Reports List */}
        <div className="bg-white rounded-2xl border border-slate-200/80 shadow-sm overflow-hidden">
          <div className="px-6 py-4 border-b border-slate-100 flex items-center justify-between">
            <h2 className="text-sm font-bold uppercase tracking-wider text-slate-700">All Past Reports</h2>
            <span className="text-xs text-slate-400">Immutable after submission</span>
          </div>

          {loading ? (
            <div className="p-12 text-center text-slate-400">
              <div className="w-7 h-7 border-3 border-blue-600 border-t-transparent rounded-full animate-spin mx-auto mb-3" />
              <p className="text-sm">Loading report history...</p>
            </div>
          ) : reports.length === 0 ? (
            <div className="p-12 text-center">
              <FileText className="w-10 h-10 text-slate-300 mx-auto mb-3" />
              <h3 className="text-base font-semibold text-slate-700">No weekly reports found</h3>
              <p className="text-xs text-slate-400 mt-1 max-w-sm mx-auto">
                Reports are generated automatically at the start of each week. Click below to start your first report.
              </p>
              <Link
                to="/employee/weekly-report"
                className="mt-4 inline-flex items-center gap-1.5 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-xl text-xs font-semibold shadow-sm transition-all"
              >
                <Plus className="w-3.5 h-3.5" /> Start Current Week Report
              </Link>
            </div>
          ) : (
            <div className="divide-y divide-slate-100">
              {reports.map((report) => {
                const isSubmitted = report.status === 'submitted';
                const hasAI = !!report.ai_summary;
                const submittedDate = report.submitted_at
                  ? new Date(report.submitted_at).toLocaleDateString(undefined, {
                      month: 'short',
                      day: 'numeric',
                      year: 'numeric',
                      hour: '2-digit',
                      minute: '2-digit',
                    })
                  : null;

                return (
                  <div
                    key={report.id}
                    className="p-5 hover:bg-slate-50/70 transition-colors flex flex-col md:flex-row md:items-center justify-between gap-4"
                  >
                    <div className="flex-1">
                      <div className="flex flex-wrap items-center gap-2.5 mb-2">
                        <span className="font-bold text-slate-900 text-base flex items-center gap-1.5">
                          <Calendar className="w-4 h-4 text-slate-400" />
                          {report.week_start_date} &rarr; {report.week_end_date}
                        </span>

                        {isSubmitted ? (
                          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-emerald-100 text-emerald-800">
                            <CheckCircle2 className="w-3 h-3" /> Submitted
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-amber-100 text-amber-800">
                            <Clock className="w-3 h-3" /> Draft In Progress
                          </span>
                        )}

                        {hasAI && (
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-semibold bg-indigo-50 text-indigo-700 border border-indigo-200/60">
                            <Sparkles className="w-3 h-3 text-indigo-500" /> AI Executive Summary
                          </span>
                        )}
                      </div>

                      {/* Excerpt */}
                      {report.ai_summary?.executive_summary ? (
                        <p className="text-xs text-slate-600 line-clamp-2 max-w-3xl mb-2 italic">
                          &ldquo;{report.ai_summary.executive_summary}&rdquo;
                        </p>
                      ) : (
                        <p className="text-xs text-slate-400 mb-2">
                          {isSubmitted ? 'Weekly report finalized.' : 'Draft not yet submitted. Complete all 4 questions to submit.'}
                        </p>
                      )}

                      <div className="flex flex-wrap items-center gap-4 text-[11px] text-slate-400 font-medium">
                        <span>Work items linked: <strong className="text-slate-600">{report.work_updates?.length || 0}</strong></span>
                        {report.manager_name && (
                          <span>Reports to: <strong className="text-slate-600">{report.manager_name}</strong></span>
                        )}
                        {submittedDate && (
                          <span>Submitted on: <strong className="text-slate-600">{submittedDate}</strong></span>
                        )}
                      </div>
                    </div>

                    {/* Actions */}
                    <div className="flex items-center gap-2.5 shrink-0">
                      {isSubmitted ? (
                        <>
                          <button
                            type="button"
                            onClick={(e) => handleDownloadPdf(e, report)}
                            disabled={downloadingId === report.id}
                            className="px-3.5 py-2 rounded-xl text-xs font-semibold border border-slate-300 hover:bg-slate-100 text-slate-700 flex items-center gap-1.5 transition-colors disabled:opacity-50"
                            title="Download PDF"
                          >
                            {downloadingId === report.id ? (
                              <div className="w-3.5 h-3.5 border-2 border-slate-700 border-t-transparent rounded-full animate-spin" />
                            ) : (
                              <Download className="w-3.5 h-3.5 text-slate-500" />
                            )}
                            PDF
                          </button>

                          <Link
                            to={`/reports/${report.id}`}
                            className="px-3.5 py-2 rounded-xl text-xs font-semibold bg-slate-900 hover:bg-slate-800 text-white flex items-center gap-1.5 transition-colors shadow-sm"
                          >
                            <Eye className="w-3.5 h-3.5" /> View Report
                          </Link>
                        </>
                      ) : (
                        <Link
                          to="/employee/weekly-report"
                          className="px-4 py-2 rounded-xl text-xs font-semibold bg-blue-600 hover:bg-blue-700 text-white flex items-center gap-1.5 transition-colors shadow-sm"
                        >
                          Continue Draft <ChevronRight className="w-3.5 h-3.5" />
                        </Link>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </main>
    </div>
  );
};
