import React, { useState, useEffect } from 'react';
import { useParams, Link, useNavigate } from 'react-router-dom';
import { Navbar } from '../components/Navbar';
import { AISummaryCard } from '../components/AISummaryCard';
import { managerService, reportService } from '../services/api';
import { 
  ArrowLeft, 
  Download, 
  Calendar, 
  User, 
  Clock, 
  FileText, 
  Layers, 
  CheckCircle2, 
  AlertCircle 
} from 'lucide-react';

export const ReportDetailView = () => {
  const { id } = useParams();
  const navigate = useNavigate();
  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [downloading, setDownloading] = useState(false);

  useEffect(() => {
    loadReport();
  }, [id]);

  const loadReport = async () => {
    setLoading(true);
    setError('');
    try {
      const res = await reportService.getReportById(id);
      setReport(res.data);
    } catch (err) {
      console.error(err);
      if (err.response?.status === 403) {
        setError('Forbidden: You do not have permission to view this report.');
      } else {
        setError('Failed to load report details.');
      }
    } finally {
      setLoading(false);
    }
  };

  const handleDownloadPdf = async () => {
    if (!report) return;
    setDownloading(true);
    try {
      await reportService.downloadPdf(
        report.id, 
        `Weekly_Report_${report.week_start_date}_${(report.user_name || 'Employee').replace(/\s+/g, '_')}.pdf`
      );
    } catch (err) {
      console.error(err);
      alert('Failed to download PDF.');
    } finally {
      setDownloading(false);
    }
  };

  return (
    <div className="min-h-screen bg-slate-50 flex flex-col">
      <Navbar />

      <main className="flex-1 max-w-5xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Navigation back */}
        <div className="mb-6">
          <Link
            to="/manager"
            className="inline-flex items-center gap-1.5 text-xs font-semibold text-slate-500 hover:text-slate-800 transition-colors"
          >
            <ArrowLeft className="w-4 h-4" />
            Back to Team Dashboard
          </Link>
        </div>

        {error && (
          <div className="bg-red-50 border border-red-200 rounded-2xl p-6 text-center text-red-800">
            <AlertCircle className="w-8 h-8 text-red-600 mx-auto mb-2" />
            <h3 className="text-base font-bold">Access Restricted</h3>
            <p className="text-sm mt-1">{error}</p>
            <button
              onClick={() => navigate('/manager')}
              className="mt-4 px-4 py-2 bg-red-600 hover:bg-red-700 text-white text-xs font-semibold rounded-xl transition-colors"
            >
              Return to Dashboard
            </button>
          </div>
        )}

        {loading ? (
          <div className="bg-white rounded-2xl p-16 text-center border border-slate-200">
            <div className="w-8 h-8 border-2 border-indigo-600 border-t-transparent rounded-full animate-spin mx-auto mb-3"></div>
            <p className="text-sm text-slate-500">Loading weekly report detail...</p>
          </div>
        ) : report && (
          <div className="space-y-6">
            {/* Top Report Info Card */}
            <div className="bg-white rounded-2xl p-6 border border-slate-200 shadow-sm flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
              <div>
                <div className="flex items-center gap-2 mb-1.5">
                  <span className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-bold uppercase tracking-wider ${
                    report.status === 'submitted'
                      ? 'bg-emerald-100 text-emerald-800'
                      : 'bg-amber-100 text-amber-800'
                  }`}>
                    {report.status === 'submitted' ? (
                      <>
                        <CheckCircle2 className="w-3 h-3" /> Submitted & Finalized
                      </>
                    ) : (
                      'Draft in Progress'
                    )}
                  </span>
                  <span className="text-xs text-slate-400">
                    Week: {report.week_start_date} → {report.week_end_date}
                  </span>
                </div>
                <h1 className="text-2xl font-extrabold text-slate-900 tracking-tight">
                  {report.user_name}'s Weekly Report
                </h1>
                <p className="text-xs text-slate-500 mt-1">
                  Employee Email: <strong className="text-slate-700">{report.user_email}</strong>
                  {report.submitted_at && (
                    <span> • Submitted on {new Date(report.submitted_at).toLocaleString()}</span>
                  )}
                </p>
              </div>

              <button
                onClick={handleDownloadPdf}
                disabled={downloading}
                className="px-4 py-2.5 bg-indigo-600 hover:bg-indigo-700 text-white font-medium rounded-xl text-xs flex items-center gap-2 shadow-sm shadow-indigo-500/20 transition-colors self-start sm:self-auto"
              >
                <Download className="w-4 h-4" />
                {downloading ? 'Exporting PDF...' : 'Download Official PDF'}
              </button>
            </div>

            {/* AI Executive Summary Card */}
            {report.ai_summary ? (
              <AISummaryCard aiSummary={report.ai_summary} />
            ) : (
              <div className="bg-amber-50 border border-amber-200 rounded-2xl p-4 text-xs text-amber-800 flex items-center gap-2">
                <AlertCircle className="w-4 h-4 text-amber-600 shrink-0" />
                <span>This report is currently in draft status; AI executive summary is generated upon employee submission.</span>
              </div>
            )}

            {/* Four Weekly Questions & Answers */}
            <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-6">
              <div className="pb-4 border-b border-slate-100 mb-6">
                <h3 className="text-base font-bold text-slate-900 flex items-center gap-2">
                  <FileText className="w-5 h-5 text-indigo-600" />
                  Weekly Reflection Answers
                </h3>
                <p className="text-xs text-slate-500 mt-1">
                  Answers provided by {report.user_name} for the four weekly evaluation prompts.
                </p>
              </div>

              <div className="space-y-6">
                {report.answers?.map((q, idx) => (
                  <div key={q.question_key || idx} className="space-y-2">
                    <h4 className="text-xs font-bold uppercase tracking-wider text-slate-700 flex items-center gap-2">
                      <span className="w-5 h-5 rounded-full bg-indigo-100 text-indigo-700 text-[11px] font-bold flex items-center justify-center">
                        {idx + 1}
                      </span>
                      {q.question_text}
                    </h4>
                    <div className="p-4 bg-slate-50 rounded-xl border border-slate-200 text-sm text-slate-800 whitespace-pre-wrap leading-relaxed">
                      {q.answer || <span className="text-slate-400 italic">No answer provided</span>}
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Daily Work Updates Attached */}
            <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-6">
              <div className="pb-4 border-b border-slate-100 mb-4">
                <h3 className="text-base font-bold text-slate-900 flex items-center gap-2">
                  <Layers className="w-5 h-5 text-blue-600" />
                  Attached Daily Work Updates ({report.work_updates?.length || 0})
                </h3>
                <p className="text-xs text-slate-500">
                  Granular task contributions logged by the employee during this reporting cycle.
                </p>
              </div>

              {report.work_updates && report.work_updates.length > 0 ? (
                <div className="divide-y divide-slate-100">
                  {report.work_updates.map((u) => (
                    <div key={u.id} className="py-3.5 space-y-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="text-xs font-bold text-slate-800 bg-slate-100 px-2 py-0.5 rounded border border-slate-200">
                          {u.date}
                        </span>
                        <span className="text-xs font-semibold text-blue-700 bg-blue-50 px-2 py-0.5 rounded">
                          {u.category}
                        </span>
                        {u.hours_spent !== null && (
                          <span className="text-xs text-slate-500 flex items-center gap-1">
                            <Clock className="w-3 h-3 text-slate-400" /> {u.hours_spent} hrs
                          </span>
                        )}
                      </div>
                      <h4 className="text-sm font-bold text-slate-900">{u.title}</h4>
                      <p className="text-xs text-slate-600 leading-relaxed whitespace-pre-wrap">
                        {u.description}
                      </p>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-xs text-slate-400 py-4 text-center">
                  No daily work updates logged for this week.
                </p>
              )}
            </div>
          </div>
        )}
      </main>
    </div>
  );
};
