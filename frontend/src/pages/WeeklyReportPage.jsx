import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { Navbar } from '../components/Navbar';
import { AISummaryCard } from '../components/AISummaryCard';
import { reportService, questionService } from '../services/api';
import { 
  FileText, 
  Save, 
  Send, 
  CheckCircle2, 
  Download, 
  Clock, 
  Calendar, 
  History, 
  AlertCircle,
  Sparkles,
  Lock,
  ChevronDown,
  Layers,
  ArrowLeft
} from 'lucide-react';

export const WeeklyReportPage = () => {
  const [report, setReport] = useState(null);
  const [answers, setAnswers] = useState({});
  const [loading, setLoading] = useState(true);
  const [savingDraft, setSavingDraft] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [feedback, setFeedback] = useState({ type: '', message: '' });
  const [historyReports, setHistoryReports] = useState([]);
  const [showHistory, setShowHistory] = useState(false);
  const [downloadingPdf, setDownloadingPdf] = useState(false);

  useEffect(() => {
    loadReport();
    loadHistory();
  }, []);

  const loadReport = async () => {
    setLoading(true);
    setFeedback({ type: '', message: '' });
    try {
      const res = await reportService.getCurrentReport();
      const currentData = res.data;
      setReport(currentData);

      // Populate answers state
      const ansMap = {};
      if (currentData.answers && currentData.answers.length > 0) {
        currentData.answers.forEach((a) => {
          ansMap[a.question_key] = a.answer || '';
        });
      }
      setAnswers(ansMap);
    } catch (err) {
      console.error(err);
      setFeedback({ type: 'error', message: 'Failed to load weekly report.' });
    } finally {
      setLoading(false);
    }
  };

  const loadHistory = async () => {
    try {
      const res = await reportService.getReportHistory();
      setHistoryReports(res.data);
    } catch (err) {
      console.error("Failed to load history:", err);
    }
  };

  const handleAnswerChange = (key, value) => {
    if (report?.status === 'submitted') return; // Read-only
    setAnswers((prev) => ({ ...prev, [key]: value }));
  };

  const prepareAnswerPayload = () => {
    if (!report || !report.answers) return [];
    return report.answers.map((a) => ({
      question_key: a.question_key,
      question_text: a.question_text,
      answer: answers[a.question_key] || '',
    }));
  };

  const handleSaveDraft = async () => {
    if (report?.status === 'submitted') return;
    setSavingDraft(true);
    setFeedback({ type: '', message: '' });
    try {
      const payload = {
        week_start_date: report.week_start_date,
        week_end_date: report.week_end_date,
        answers: prepareAnswerPayload(),
      };
      const res = await reportService.saveDraft(payload);
      setReport(res.data);
      setFeedback({ type: 'success', message: 'Draft saved successfully!' });
      setTimeout(() => setFeedback({ type: '', message: '' }), 3000);
    } catch (err) {
      console.error(err);
      setFeedback({ type: 'error', message: err.response?.data?.detail || 'Failed to save draft.' });
    } finally {
      setSavingDraft(false);
    }
  };

  const handleSubmitReport = async () => {
    if (report?.status === 'submitted') return;

    // Check if at least one question is answered
    const hasAnswers = Object.values(answers).some((val) => val && val.trim().length > 0);
    if (!hasAnswers) {
      setFeedback({
        type: 'error',
        message: 'Please provide answers to the reflection questions before submitting.'
      });
      return;
    }

    const confirmSubmit = window.confirm(
      "Are you sure you want to submit your weekly report?\n\nOnce submitted, the report becomes read-only, an AI executive summary will be generated, and your manager will be notified."
    );
    if (!confirmSubmit) return;

    setSubmitting(true);
    setFeedback({ type: '', message: '' });
    try {
      const payload = {
        answers: prepareAnswerPayload(),
      };
      const res = await reportService.submitReport(report.id, payload);
      setReport(res.data);
      setFeedback({
        type: 'success',
        message: '🎉 Report submitted successfully! AI Executive Summary has been generated.'
      });
      await loadHistory();
    } catch (err) {
      console.error(err);
      setFeedback({
        type: 'error',
        message: err.response?.data?.detail || 'Failed to submit report. Please try again.'
      });
    } finally {
      setSubmitting(false);
    }
  };

  const handleDownloadPdf = async (reportId) => {
    setDownloadingPdf(true);
    try {
      const targetId = reportId || report?.id;
      await reportService.downloadPdf(targetId, `Weekly_Report_${report?.week_start_date}.pdf`);
    } catch (err) {
      console.error("PDF download failed:", err);
      alert("Failed to download PDF. Please try again.");
    } finally {
      setDownloadingPdf(false);
    }
  };

  const isSubmitted = report?.status === 'submitted';

  return (
    <div className="min-h-screen bg-slate-50 flex flex-col">
      <Navbar />

      <main className="flex-1 max-w-5xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Header Navigation */}
        <div className="flex items-center justify-between mb-6">
          <Link
            to="/employee"
            className="inline-flex items-center gap-1.5 text-xs font-semibold text-slate-500 hover:text-slate-800 transition-colors"
          >
            <ArrowLeft className="w-4 h-4" />
            Back to Dashboard
          </Link>

          <button
            onClick={() => setShowHistory(!showHistory)}
            className="inline-flex items-center gap-1.5 text-xs font-semibold text-blue-600 hover:text-blue-700 bg-blue-50 px-3 py-1.5 rounded-xl border border-blue-200 transition-colors"
          >
            <History className="w-3.5 h-3.5" />
            Past Reports ({historyReports.length})
          </button>
        </div>

        {/* History Drawer / Modal */}
        {showHistory && (
          <div className="mb-8 p-5 bg-white rounded-2xl border border-slate-200 shadow-sm animate-in fade-in duration-150">
            <div className="flex items-center justify-between pb-3 border-b border-slate-100 mb-3">
              <h3 className="font-bold text-slate-900 text-sm flex items-center gap-2">
                <History className="w-4 h-4 text-blue-600" /> Past Weekly Reports History
              </h3>
              <button
                onClick={() => setShowHistory(false)}
                className="text-xs text-slate-400 hover:text-slate-600"
              >
                Close
              </button>
            </div>

            <div className="space-y-2 max-h-60 overflow-y-auto pr-1">
              {historyReports.map((r) => (
                <div
                  key={r.id}
                  className="p-3 bg-slate-50 hover:bg-blue-50/50 rounded-xl border border-slate-200 flex items-center justify-between transition-colors text-xs"
                >
                  <div className="flex items-center gap-3">
                    <span className={`w-2 h-2 rounded-full ${
                      r.status === 'submitted' ? 'bg-emerald-500' : 'bg-amber-500'
                    }`}></span>
                    <div>
                      <span className="font-bold text-slate-900 block">
                        Week: {r.week_start_date} to {r.week_end_date}
                      </span>
                      <span className="text-slate-500 text-[11px]">
                        Status: {r.status === 'submitted' ? 'Submitted' : 'Draft'} • {r.work_updates?.length || 0} logged updates
                      </span>
                    </div>
                  </div>

                  <div className="flex items-center gap-2">
                    {r.status === 'submitted' && (
                      <button
                        onClick={() => handleDownloadPdf(r.id)}
                        className="px-2.5 py-1 text-[11px] bg-white border border-slate-200 rounded-lg hover:bg-slate-100 text-slate-700 flex items-center gap-1"
                      >
                        <Download className="w-3 h-3" /> PDF
                      </button>
                    )}
                    <button
                      onClick={() => {
                        setReport(r);
                        const ansMap = {};
                        (r.answers || []).forEach((a) => {
                          ansMap[a.question_key] = a.answer || '';
                        });
                        setAnswers(ansMap);
                        setShowHistory(false);
                      }}
                      className="px-2.5 py-1 text-[11px] bg-blue-600 hover:bg-blue-700 text-white rounded-lg font-medium"
                    >
                      View
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Feedback alert */}
        {feedback.message && (
          <div className={`mb-6 p-4 rounded-2xl border flex items-start gap-3 text-sm animate-in fade-in duration-150 ${
            feedback.type === 'success'
              ? 'bg-emerald-50 border-emerald-200 text-emerald-800'
              : 'bg-red-50 border-red-200 text-red-800'
          }`}>
            {feedback.type === 'success' ? (
              <CheckCircle2 className="w-5 h-5 text-emerald-600 shrink-0 mt-0.5" />
            ) : (
              <AlertCircle className="w-5 h-5 text-red-600 shrink-0 mt-0.5" />
            )}
            <div className="flex-1 font-medium">{feedback.message}</div>
          </div>
        )}

        {loading ? (
          <div className="bg-white rounded-2xl p-16 text-center border border-slate-200">
            <div className="w-8 h-8 border-2 border-blue-600 border-t-transparent rounded-full animate-spin mx-auto mb-3"></div>
            <p className="text-sm text-slate-500">Loading weekly report...</p>
          </div>
        ) : (
          <div className="space-y-6">
            {/* Top Status Card */}
            <div className="bg-white rounded-2xl p-6 border border-slate-200 shadow-sm flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
              <div>
                <div className="flex items-center gap-2 mb-1.5">
                  <span className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-bold uppercase tracking-wider ${
                    isSubmitted
                      ? 'bg-emerald-100 text-emerald-800'
                      : 'bg-amber-100 text-amber-800'
                  }`}>
                    {isSubmitted ? (
                      <>
                        <Lock className="w-3 h-3" /> Submitted • Read-Only
                      </>
                    ) : (
                      <>
                        <FileText className="w-3 h-3" /> Draft in Progress
                      </>
                    )}
                  </span>
                  <span className="text-xs text-slate-400">
                    Week: {report?.week_start_date} → {report?.week_end_date}
                  </span>
                </div>
                <h1 className="text-xl sm:text-2xl font-extrabold text-slate-900 tracking-tight">
                  Weekly Accountability Report
                </h1>
                <p className="text-xs text-slate-500 mt-1">
                  Assigned Manager: <strong className="text-slate-700">{report?.manager_name || 'Sarah Chen'}</strong>
                  {report?.submitted_at && (
                    <span> • Submitted on {new Date(report.submitted_at).toLocaleString()}</span>
                  )}
                </p>
              </div>

              {/* Action Buttons */}
              <div className="flex flex-wrap items-center gap-2.5">
                {isSubmitted && (
                  <button
                    onClick={() => handleDownloadPdf()}
                    disabled={downloadingPdf}
                    className="px-4 py-2 bg-slate-100 hover:bg-slate-200 text-slate-700 font-medium rounded-xl text-xs flex items-center gap-1.5 transition-colors"
                  >
                    <Download className="w-3.5 h-3.5" />
                    {downloadingPdf ? 'Generating PDF...' : 'Download PDF'}
                  </button>
                )}

                {!isSubmitted && (
                  <>
                    <button
                      onClick={handleSaveDraft}
                      disabled={savingDraft || submitting}
                      className="px-4 py-2 bg-white border border-slate-200 hover:bg-slate-50 text-slate-700 font-medium rounded-xl text-xs flex items-center gap-1.5 shadow-sm transition-colors disabled:opacity-50"
                    >
                      <Save className="w-3.5 h-3.5" />
                      {savingDraft ? 'Saving Draft...' : 'Save Draft'}
                    </button>

                    <button
                      onClick={handleSubmitReport}
                      disabled={submitting || savingDraft}
                      className="px-5 py-2 bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-700 hover:to-indigo-700 text-white font-semibold rounded-xl text-xs flex items-center gap-1.5 shadow-md shadow-blue-500/25 transition-all disabled:opacity-50"
                    >
                      <Send className="w-3.5 h-3.5" />
                      {submitting ? 'Generating AI Summary...' : 'Submit Weekly Report'}
                    </button>
                  </>
                )}
              </div>
            </div>

            {/* AI Summary Section (If Submitted) */}
            {isSubmitted && report?.ai_summary && (
              <AISummaryCard aiSummary={report.ai_summary} />
            )}

            {/* Four Weekly Questions Form */}
            <div className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden p-6">
              <div className="pb-4 border-b border-slate-100 mb-6">
                <h3 className="text-base font-bold text-slate-900 flex items-center gap-2">
                  <FileText className="w-5 h-5 text-blue-600" />
                  Weekly Reflection Questions
                </h3>
                <p className="text-xs text-slate-500 mt-1">
                  {isSubmitted
                    ? 'This report has been submitted to your manager and is locked in read-only mode.'
                    : 'Please provide clear, concise answers to these four weekly questions. You may save your progress anytime.'}
                </p>
              </div>

              <div className="space-y-6">
                {report?.answers && report.answers.length > 0 ? (
                  report.answers.map((q, idx) => (
                    <div key={q.question_key || idx} className="space-y-2">
                      <label className="block text-xs font-bold uppercase tracking-wider text-slate-700 flex items-center gap-2">
                        <span className="w-5 h-5 rounded-full bg-blue-100 text-blue-700 text-[11px] font-bold flex items-center justify-center">
                          {idx + 1}
                        </span>
                        {q.question_text}
                      </label>
                      <textarea
                        rows={3}
                        disabled={isSubmitted}
                        value={answers[q.question_key] || ''}
                        onChange={(e) => handleAnswerChange(q.question_key, e.target.value)}
                        placeholder={
                          isSubmitted
                            ? 'No answer provided.'
                            : `Write your response for ${q.question_text.toLowerCase()}...`
                        }
                        className={`w-full p-3.5 text-sm rounded-xl border focus:outline-none transition-colors ${
                          isSubmitted
                            ? 'bg-slate-50/80 border-slate-200 text-slate-800 cursor-not-allowed resize-none'
                            : 'bg-white border-slate-200 focus:ring-2 focus:ring-blue-500'
                        }`}
                      />
                    </div>
                  ))
                ) : (
                  <p className="text-sm text-slate-500">No questions loaded.</p>
                )}
              </div>

              {!isSubmitted && (
                <div className="mt-8 pt-4 border-t border-slate-100 flex items-center justify-between">
                  <span className="text-xs text-slate-400">
                    * Submitting will trigger the AI summary generator and notify your manager.
                  </span>
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={handleSaveDraft}
                      disabled={savingDraft || submitting}
                      className="px-4 py-2 border border-slate-200 hover:bg-slate-50 text-slate-700 text-xs font-medium rounded-xl transition-colors"
                    >
                      {savingDraft ? 'Saving...' : 'Save Draft'}
                    </button>
                    <button
                      type="button"
                      onClick={handleSubmitReport}
                      disabled={submitting || savingDraft}
                      className="px-5 py-2 bg-blue-600 hover:bg-blue-700 text-white text-xs font-semibold rounded-xl shadow-sm transition-colors"
                    >
                      {submitting ? 'Submitting...' : 'Submit Report'}
                    </button>
                  </div>
                </div>
              )}
            </div>

            {/* Daily Work Updates Attached to this Week */}
            <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-6">
              <div className="flex items-center justify-between pb-4 border-b border-slate-100 mb-4">
                <div>
                  <h3 className="text-base font-bold text-slate-900 flex items-center gap-2">
                    <Layers className="w-5 h-5 text-indigo-600" />
                    Daily Work Updates for this Week ({report?.work_updates?.length || 0})
                  </h3>
                  <p className="text-xs text-slate-500">
                    These logged tasks are automatically synthesized into your weekly AI summary.
                  </p>
                </div>

                {!isSubmitted && (
                  <Link
                    to="/employee"
                    className="text-xs font-semibold text-blue-600 hover:text-blue-700"
                  >
                    + Add / Edit Updates
                  </Link>
                )}
              </div>

              {report?.work_updates && report.work_updates.length > 0 ? (
                <div className="divide-y divide-slate-100">
                  {report.work_updates.map((u) => (
                    <div key={u.id} className="py-3 flex items-start justify-between gap-4">
                      <div>
                        <div className="flex items-center gap-2 mb-1">
                          <span className="text-[11px] font-bold text-slate-700 bg-slate-100 px-2 py-0.5 rounded">
                            {u.date}
                          </span>
                          <span className="text-[11px] font-semibold text-indigo-700 bg-indigo-50 px-2 py-0.5 rounded">
                            {u.category}
                          </span>
                          {u.hours_spent !== null && (
                            <span className="text-[11px] text-slate-500 flex items-center gap-1">
                              <Clock className="w-3 h-3" /> {u.hours_spent} hrs
                            </span>
                          )}
                        </div>
                        <h4 className="text-xs font-bold text-slate-800">{u.title}</h4>
                        <p className="text-xs text-slate-500 mt-0.5">{u.description}</p>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="py-8 text-center text-slate-400">
                  <p className="text-xs">No daily work updates logged for this week yet.</p>
                  {!isSubmitted && (
                    <Link
                      to="/employee"
                      className="mt-2 inline-block text-xs font-semibold text-blue-600 hover:underline"
                    >
                      Log updates in your dashboard
                    </Link>
                  )}
                </div>
              )}
            </div>
          </div>
        )}
      </main>
    </div>
  );
};
