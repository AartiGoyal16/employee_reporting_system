import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { Navbar } from '../components/Navbar';
import { QuestionConfigModal } from '../components/QuestionConfigModal';
import { managerService, reportService } from '../services/api';
import { 
  Users, 
  FileText, 
  Download, 
  CheckCircle2, 
  Clock, 
  Sparkles, 
  ChevronRight, 
  Filter, 
  Settings,
  AlertCircle,
  Eye,
  Calendar,
  Bell
} from 'lucide-react';

export const ManagerDashboard = () => {
  const [employees, setEmployees] = useState([]);
  const [reports, setReports] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedEmployee, setSelectedEmployee] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [isQuestionModalOpen, setIsQuestionModalOpen] = useState(false);
  const [downloadingId, setDownloadingId] = useState(null);
  const [sendingReminders, setSendingReminders] = useState(false);
  const [reminderToast, setReminderToast] = useState(null);

  const handleSendReminders = async () => {
    setSendingReminders(true);
    setReminderToast(null);
    try {
      const res = await managerService.sendReminders();
      const data = res.data;
      if (data.status === 'success') {
        setReminderToast({ type: 'success', message: data.message || `Deadline reminders sent to ${data.sent_count} team members!` });
      } else if (data.status === 'partial_success') {
        setReminderToast({ type: 'warning', message: data.message });
      } else if (data.status === 'failed' || data.status === 'smtp_not_configured') {
        setReminderToast({ type: 'error', message: data.message });
      } else {
        // Zero emails sent: all_submitted, already_reminded, no_eligible
        setReminderToast({ type: 'info', message: data.message });
      }
      setTimeout(() => setReminderToast(null), 6000);
    } catch (err) {
      setReminderToast({ type: 'error', message: 'Failed to send reminders.' });
    } finally {
      setSendingReminders(false);
    }
  };

  useEffect(() => {
    loadDashboard();
  }, [selectedEmployee, statusFilter]);

  const loadDashboard = async () => {
    setLoading(true);
    try {
      const [empRes, reportsRes] = await Promise.all([
        managerService.getEmployees(),
        managerService.getReports({
          employee_id: selectedEmployee || undefined,
          status_filter: statusFilter || undefined,
        })
      ]);
      setEmployees(empRes.data);
      setReports(reportsRes.data);
    } catch (err) {
      console.error("Failed to load manager dashboard:", err);
    } finally {
      setLoading(false);
    }
  };

  const handleDownloadPdf = async (reportId, empName, weekStart) => {
    setDownloadingId(reportId);
    try {
      await reportService.downloadPdf(reportId, `Weekly_Report_${weekStart}_${empName.replace(/\s+/g, '_')}.pdf`);
    } catch (err) {
      console.error(err);
      alert("Failed to download PDF.");
    } finally {
      setDownloadingId(null);
    }
  };

  // Metrics
  const submittedReports = reports.filter((r) => r.status === 'submitted');
  const pendingReports = reports.filter((r) => r.status === 'draft');

  return (
    <div className="min-h-screen bg-slate-50 flex flex-col">
      <Navbar onOpenQuestionModal={() => setIsQuestionModalOpen(true)} />

      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Top Header */}
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 mb-8">
          <div>
            <h1 className="text-2xl sm:text-3xl font-extrabold text-slate-900 tracking-tight">
              Manager Dashboard
            </h1>
            <p className="text-sm text-slate-500 mt-1">
              Review weekly accountability submissions and AI-synthesized summaries for your team.
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <button
              onClick={handleSendReminders}
              disabled={sendingReminders}
              className="px-4 py-2 bg-amber-500 hover:bg-amber-600 text-white text-xs font-semibold rounded-xl shadow-sm flex items-center gap-2 transition-colors disabled:opacity-50"
              title="Send deadline reminders to direct reports who have not submitted yet this week"
            >
              {sendingReminders ? (
                <div className="w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full animate-spin" />
              ) : (
                <Bell className="w-3.5 h-3.5" />
              )}
              <span>Remind Team</span>
            </button>

            <Link
              to="/manager/questions"
              className="px-4 py-2 bg-white border border-slate-200 hover:bg-slate-50 text-slate-700 text-xs font-semibold rounded-xl shadow-sm flex items-center gap-2 transition-colors"
            >
              <Settings className="w-4 h-4 text-indigo-600" />
              <span>Configure Weekly Questions</span>
            </Link>
          </div>
        </div>

        {/* Reminder Toast Alert */}
        {reminderToast && (
          <div className={`p-4 rounded-2xl text-xs font-semibold flex items-center gap-2 mb-6 shadow-sm border ${
            reminderToast.type === 'success'
              ? 'bg-emerald-50 text-emerald-800 border-emerald-200'
              : reminderToast.type === 'warning'
              ? 'bg-amber-50 text-amber-800 border-amber-200'
              : reminderToast.type === 'info'
              ? 'bg-blue-50 text-blue-800 border-blue-200'
              : 'bg-red-50 text-red-800 border-red-200'
          }`}>
            {reminderToast.type === 'success' ? (
              <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" />
            ) : reminderToast.type === 'info' ? (
              <Bell className="w-4 h-4 text-blue-600 shrink-0" />
            ) : (
              <AlertCircle className="w-4 h-4 text-amber-600 shrink-0" />
            )}
            <span>{reminderToast.message}</span>
          </div>
        )}

        {/* Metric Cards */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-5 mb-8">
          <div className="bg-white p-5 rounded-2xl border border-slate-200/80 shadow-sm flex items-center gap-4">
            <div className="w-12 h-12 rounded-xl bg-purple-50 text-purple-700 flex items-center justify-center shrink-0">
              <Users className="w-6 h-6" />
            </div>
            <div>
              <span className="text-xs font-semibold uppercase tracking-wider text-slate-400 block">
                Assigned Team Members
              </span>
              <span className="text-2xl font-bold text-slate-900 mt-0.5 block">
                {employees.length}
              </span>
            </div>
          </div>

          <div className="bg-white p-5 rounded-2xl border border-slate-200/80 shadow-sm flex items-center gap-4">
            <div className="w-12 h-12 rounded-xl bg-emerald-50 text-emerald-600 flex items-center justify-center shrink-0">
              <CheckCircle2 className="w-6 h-6" />
            </div>
            <div>
              <span className="text-xs font-semibold uppercase tracking-wider text-slate-400 block">
                Reports Submitted & Summarized
              </span>
              <span className="text-2xl font-bold text-slate-900 mt-0.5 block">
                {submittedReports.length}
              </span>
            </div>
          </div>

          <div className="bg-white p-5 rounded-2xl border border-slate-200/80 shadow-sm flex items-center gap-4">
            <div className="w-12 h-12 rounded-xl bg-amber-50 text-amber-600 flex items-center justify-center shrink-0">
              <Clock className="w-6 h-6" />
            </div>
            <div>
              <span className="text-xs font-semibold uppercase tracking-wider text-slate-400 block">
                In-Progress Drafts
              </span>
              <span className="text-2xl font-bold text-slate-900 mt-0.5 block">
                {pendingReports.length}
              </span>
            </div>
          </div>
        </div>

        {/* Assigned Team Members Row */}
        <div className="mb-8">
          <h2 className="text-xs font-semibold uppercase tracking-wider text-slate-500 mb-3">
            Your Assigned Direct Reports
          </h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-4">
            {employees.map((emp) => (
              <div
                key={emp.id}
                className="bg-white p-4 rounded-xl border border-slate-200/80 shadow-sm flex items-center justify-between"
              >
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-full bg-blue-100 text-blue-700 font-bold flex items-center justify-center text-sm">
                    {emp.name.charAt(0)}
                  </div>
                  <div>
                    <h3 className="text-sm font-bold text-slate-900 leading-tight">{emp.name}</h3>
                    <p className="text-xs text-slate-500">{emp.email}</p>
                  </div>
                </div>
                <span className="text-[10px] font-semibold text-slate-500 bg-slate-100 px-2 py-0.5 rounded-full">
                  {emp.department || 'Engineering'}
                </span>
              </div>
            ))}
          </div>
        </div>

        {/* Reports Table / Card List */}
        <div className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
          {/* Filter Bar */}
          <div className="p-5 border-b border-slate-100 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 bg-slate-50/60">
            <div>
              <h2 className="text-lg font-bold text-slate-900">Weekly Reports Overview</h2>
              <p className="text-xs text-slate-500">
                Reports belonging strictly to your assigned team members.
              </p>
            </div>

            <div className="flex flex-wrap items-center gap-3">
              {/* Filter by Employee */}
              <div className="flex items-center gap-1.5 bg-white border border-slate-200 rounded-xl px-3 py-1.5 text-xs shadow-sm">
                <span className="text-slate-400 font-medium">Employee:</span>
                <select
                  value={selectedEmployee}
                  onChange={(e) => setSelectedEmployee(e.target.value)}
                  className="bg-transparent focus:outline-none text-slate-800 font-medium cursor-pointer"
                >
                  <option value="">All Team Members</option>
                  {employees.map((e) => (
                    <option key={e.id} value={e.id}>
                      {e.name}
                    </option>
                  ))}
                </select>
              </div>

              {/* Filter by Status */}
              <div className="flex items-center gap-1.5 bg-white border border-slate-200 rounded-xl px-3 py-1.5 text-xs shadow-sm">
                <span className="text-slate-400 font-medium">Status:</span>
                <select
                  value={statusFilter}
                  onChange={(e) => setStatusFilter(e.target.value)}
                  className="bg-transparent focus:outline-none text-slate-800 font-medium cursor-pointer"
                >
                  <option value="">All Statuses</option>
                  <option value="submitted">Submitted Only</option>
                  <option value="draft">Draft Only</option>
                </select>
              </div>
            </div>
          </div>

          {/* List of Reports */}
          {loading ? (
            <div className="p-16 text-center text-slate-500">
              <div className="w-8 h-8 border-2 border-indigo-600 border-t-transparent rounded-full animate-spin mx-auto mb-3"></div>
              <p className="text-sm">Loading team reports...</p>
            </div>
          ) : reports.length === 0 ? (
            <div className="p-16 text-center text-slate-500">
              <FileText className="w-12 h-12 text-slate-300 mx-auto mb-3" />
              <h3 className="text-sm font-semibold text-slate-800">No reports found</h3>
              <p className="text-xs text-slate-400 mt-1 max-w-sm mx-auto">
                No reports found matching your current filter criteria.
              </p>
            </div>
          ) : (
            <div className="divide-y divide-slate-100">
              {reports.map((report) => {
                const isSub = report.status === 'submitted';
                const ai = report.ai_summary;

                return (
                  <div
                    key={report.id}
                    className="p-6 hover:bg-slate-50/70 transition-colors flex flex-col md:flex-row md:items-start justify-between gap-6"
                  >
                    <div className="flex-1 space-y-3">
                      <div className="flex flex-wrap items-center gap-2.5">
                        <span className="font-bold text-slate-900 text-sm">
                          {report.user_name || 'Team Member'}
                        </span>
                        <span className="text-xs text-slate-400">•</span>
                        <span className="text-xs font-semibold text-slate-600 bg-slate-100 px-2 py-0.5 rounded-lg border border-slate-200 flex items-center gap-1">
                          <Calendar className="w-3 h-3 text-slate-400" />
                          Week: {report.week_start_date} → {report.week_end_date}
                        </span>
                        <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full uppercase tracking-wider ${
                          isSub
                            ? 'bg-emerald-100 text-emerald-800'
                            : 'bg-amber-100 text-amber-800'
                        }`}>
                          {isSub ? 'Submitted' : 'Draft'}
                        </span>
                      </div>

                      {/* AI Executive Summary Snippet */}
                      {ai && (
                        <div className="bg-indigo-50/70 border border-indigo-100 rounded-xl p-3.5 space-y-1.5">
                          <div className="flex items-center gap-1.5 text-xs font-bold text-indigo-900">
                            <Sparkles className="w-3.5 h-3.5 text-amber-500" />
                            <span>AI Executive Summary</span>
                            <span className="text-[10px] font-medium text-indigo-500 ml-1">
                              ({ai.model_used || 'Gemini'})
                            </span>
                          </div>
                          <p className="text-xs text-slate-700 leading-relaxed line-clamp-2">
                            {ai.executive_summary}
                          </p>
                        </div>
                      )}

                      {/* Work Updates preview count */}
                      <div className="text-xs text-slate-500 flex items-center gap-4">
                        <span>
                          <strong>{report.work_updates?.length || 0}</strong> daily work updates attached
                        </span>
                        <span>•</span>
                        <span>
                          <strong>{report.answers?.filter((a) => a.answer)?.length || 0} / 4</strong> questions answered
                        </span>
                        {report.submitted_at && (
                          <>
                            <span>•</span>
                            <span>Submitted: {new Date(report.submitted_at).toLocaleDateString()}</span>
                          </>
                        )}
                      </div>
                    </div>

                    {/* Action buttons */}
                    <div className="flex items-center gap-2.5 shrink-0">
                      {isSub && (
                        <button
                          onClick={() => handleDownloadPdf(report.id, report.user_name, report.week_start_date)}
                          disabled={downloadingId === report.id}
                          className="px-3 py-2 bg-white border border-slate-200 hover:bg-slate-100 text-slate-700 text-xs font-medium rounded-xl flex items-center gap-1.5 shadow-sm transition-colors"
                        >
                          <Download className="w-3.5 h-3.5" />
                          {downloadingId === report.id ? 'Exporting...' : 'PDF'}
                        </button>
                      )}

                      <Link
                        to={`/manager/reports/${report.id}`}
                        className="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-semibold rounded-xl flex items-center gap-1.5 shadow-sm shadow-indigo-500/20 transition-colors"
                      >
                        <Eye className="w-3.5 h-3.5" />
                        <span>Inspect Full Report</span>
                      </Link>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </main>

      <QuestionConfigModal
        isOpen={isQuestionModalOpen}
        onClose={() => setIsQuestionModalOpen(false)}
      />
    </div>
  );
};
