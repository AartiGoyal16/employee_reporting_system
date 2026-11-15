import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { Navbar } from '../components/Navbar';
import { questionService } from '../services/api';
import {
  Settings,
  Plus,
  Trash2,
  Edit2,
  Check,
  X,
  AlertCircle,
  ArrowLeft,
  CheckCircle2,
  HelpCircle,
  ToggleLeft,
  ToggleRight
} from 'lucide-react';

export const QuestionManagerPage = () => {
  const [questions, setQuestions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [successMsg, setSuccessMsg] = useState('');
  const [newKey, setNewKey] = useState('');
  const [newText, setNewText] = useState('');
  const [adding, setAdding] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [editText, setEditText] = useState('');

  useEffect(() => {
    loadQuestions();
  }, []);

  const loadQuestions = async () => {
    setLoading(true);
    setError('');
    try {
      const res = await questionService.getQuestions({ include_inactive: true });
      setQuestions(res.data);
    } catch (err) {
      console.error(err);
      setError('Failed to load questions.');
    } finally {
      setLoading(false);
    }
  };

  const handleAddQuestion = async (e) => {
    e.preventDefault();
    if (!newKey.trim() || !newText.trim()) return;
    setAdding(true);
    setError('');
    setSuccessMsg('');
    try {
      await questionService.createQuestion({
        key: newKey.trim().toLowerCase().replace(/\s+/g, '_'),
        question_text: newText.trim(),
        order: questions.length + 1,
        is_active: true
      });
      setNewKey('');
      setNewText('');
      setSuccessMsg('New question added successfully!');
      await loadQuestions();
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to add question');
    } finally {
      setAdding(false);
    }
  };

  const handleToggle = async (id) => {
    setError('');
    try {
      await questionService.toggleQuestion(id);
      await loadQuestions();
    } catch (err) {
      setError('Could not update question status.');
    }
  };

  const handleDelete = async (id) => {
    if (!window.confirm('Are you sure you want to remove this question from future reports?')) return;
    setError('');
    try {
      await questionService.deleteQuestion(id);
      setSuccessMsg('Question deleted.');
      await loadQuestions();
    } catch (err) {
      setError('Failed to delete question.');
    }
  };

  const startEdit = (q) => {
    setEditingId(q.id);
    setEditText(q.question_text);
  };

  const cancelEdit = () => {
    setEditingId(null);
    setEditText('');
  };

  const handleSaveEdit = async (id) => {
    if (!editText.trim()) return;
    try {
      await questionService.updateQuestion(id, { question_text: editText.trim() });
      setEditingId(null);
      await loadQuestions();
    } catch (err) {
      setError('Could not save question changes.');
    }
  };

  return (
    <div className="min-h-screen bg-slate-50 flex flex-col">
      <Navbar />

      <main className="flex-1 max-w-5xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Header */}
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 mb-8">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <Link
                to="/manager"
                className="text-xs font-semibold text-slate-500 hover:text-slate-800 flex items-center gap-1 transition-colors"
              >
                <ArrowLeft className="w-3.5 h-3.5" /> Back to Team Dashboard
              </Link>
            </div>
            <h1 className="text-2xl sm:text-3xl font-extrabold text-slate-900 tracking-tight flex items-center gap-2.5">
              <Settings className="w-7 h-7 text-indigo-600" />
              Configure Weekly Questions
            </h1>
            <p className="text-sm text-slate-500 mt-1">
              Customize the weekly reflection questions answered by employees for weekly report submissions.
            </p>
          </div>
        </div>

        {/* Notifications / Alerts */}
        {error && (
          <div className="p-4 bg-red-50 border border-red-200 rounded-2xl text-sm text-red-700 flex items-center gap-3 mb-6">
            <AlertCircle className="w-5 h-5 shrink-0 text-red-500" />
            <span>{error}</span>
          </div>
        )}

        {successMsg && (
          <div className="p-4 bg-emerald-50 border border-emerald-200 rounded-2xl text-sm text-emerald-800 flex items-center gap-3 mb-6">
            <CheckCircle2 className="w-5 h-5 shrink-0 text-emerald-600" />
            <span>{successMsg}</span>
          </div>
        )}

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
          {/* Questions List */}
          <div className="lg:col-span-2 space-y-4">
            <div className="bg-white rounded-2xl border border-slate-200/80 shadow-sm overflow-hidden">
              <div className="px-6 py-4 border-b border-slate-100 flex items-center justify-between">
                <div>
                  <h2 className="text-sm font-bold uppercase tracking-wider text-slate-800">
                    Weekly Report Questions ({questions.length})
                  </h2>
                  <p className="text-xs text-slate-400 mt-0.5">
                    Active questions will be presented to employees in their weekly draft.
                  </p>
                </div>
              </div>

              {loading ? (
                <div className="p-12 text-center text-slate-400">
                  <div className="w-6 h-6 border-2 border-indigo-600 border-t-transparent rounded-full animate-spin mx-auto mb-2" />
                  <p className="text-xs">Loading questions...</p>
                </div>
              ) : questions.length === 0 ? (
                <div className="p-8 text-center text-slate-400 text-xs">
                  No questions configured. Add your first question below.
                </div>
              ) : (
                <div className="divide-y divide-slate-100">
                  {questions.map((q, idx) => {
                    const isEditing = editingId === q.id;

                    return (
                      <div
                        key={q.id || idx}
                        className={`p-5 transition-colors ${q.is_active ? 'bg-white' : 'bg-slate-50/70 opacity-75'}`}
                      >
                        <div className="flex items-start justify-between gap-4">
                          <div className="flex items-start gap-3 flex-1">
                            <span className="w-6 h-6 rounded-full bg-indigo-50 text-indigo-700 font-bold text-xs flex items-center justify-center shrink-0 mt-0.5">
                              {idx + 1}
                            </span>
                            <div className="flex-1">
                              {isEditing ? (
                                <div className="space-y-2">
                                  <textarea
                                    value={editText}
                                    onChange={(e) => setEditText(e.target.value)}
                                    className="w-full p-2.5 text-xs border border-indigo-300 rounded-xl focus:ring-2 focus:ring-indigo-500 focus:outline-none"
                                    rows={2}
                                  />
                                  <div className="flex items-center gap-2">
                                    <button
                                      type="button"
                                      onClick={() => handleSaveEdit(q.id)}
                                      className="px-2.5 py-1 bg-indigo-600 text-white rounded-lg text-xs font-semibold flex items-center gap-1"
                                    >
                                      <Check className="w-3 h-3" /> Save
                                    </button>
                                    <button
                                      type="button"
                                      onClick={cancelEdit}
                                      className="px-2.5 py-1 bg-slate-200 text-slate-700 rounded-lg text-xs font-semibold flex items-center gap-1"
                                    >
                                      <X className="w-3 h-3" /> Cancel
                                    </button>
                                  </div>
                                </div>
                              ) : (
                                <>
                                  <p className="text-sm font-semibold text-slate-900">{q.question_text}</p>
                                  <div className="flex items-center gap-3 mt-1.5">
                                    <span className="text-[11px] font-mono text-slate-400 bg-slate-100 px-2 py-0.5 rounded">
                                      key: {q.key}
                                    </span>
                                    {q.is_active ? (
                                      <span className="text-[11px] font-semibold text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded-full flex items-center gap-1">
                                        <Check className="w-3 h-3" /> Active
                                      </span>
                                    ) : (
                                      <span className="text-[11px] font-semibold text-slate-500 bg-slate-200 px-2 py-0.5 rounded-full">
                                        Inactive
                                      </span>
                                    )}
                                  </div>
                                </>
                              )}
                            </div>
                          </div>

                          {/* Action icons */}
                          {!isEditing && (
                            <div className="flex items-center gap-1.5 shrink-0">
                              <button
                                type="button"
                                onClick={() => handleToggle(q.id)}
                                title={q.is_active ? 'Deactivate question' : 'Activate question'}
                                className="p-1.5 rounded-lg text-slate-400 hover:text-indigo-600 hover:bg-indigo-50 transition-colors"
                              >
                                {q.is_active ? (
                                  <ToggleRight className="w-5 h-5 text-indigo-600" />
                                ) : (
                                  <ToggleLeft className="w-5 h-5 text-slate-400" />
                                )}
                              </button>

                              <button
                                type="button"
                                onClick={() => startEdit(q)}
                                title="Edit question prompt"
                                className="p-1.5 rounded-lg text-slate-400 hover:text-slate-700 hover:bg-slate-100 transition-colors"
                              >
                                <Edit2 className="w-4 h-4" />
                              </button>

                              <button
                                type="button"
                                onClick={() => handleDelete(q.id)}
                                title="Delete question"
                                className="p-1.5 rounded-lg text-slate-400 hover:text-red-600 hover:bg-red-50 transition-colors"
                              >
                                <Trash2 className="w-4 h-4" />
                              </button>
                            </div>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          </div>

          {/* Add Question Card */}
          <div>
            <div className="bg-white p-6 rounded-2xl border border-slate-200/80 shadow-sm sticky top-24">
              <div className="flex items-center gap-2 mb-4">
                <HelpCircle className="w-5 h-5 text-indigo-600" />
                <h3 className="font-bold text-slate-900 text-sm">Add New Question</h3>
              </div>

              <form onSubmit={handleAddQuestion} className="space-y-4">
                <div>
                  <label className="block text-xs font-semibold uppercase tracking-wider text-slate-600 mb-1">
                    Question Key Identifier
                  </label>
                  <input
                    type="text"
                    value={newKey}
                    onChange={(e) => setNewKey(e.target.value)}
                    placeholder="e.g. blockers, priorities"
                    className="w-full px-3 py-2 text-xs border border-slate-300 rounded-xl focus:ring-2 focus:ring-indigo-500 focus:outline-none"
                    required
                  />
                  <p className="text-[10px] text-slate-400 mt-1">
                    Used internally and by AI prompt summarization.
                  </p>
                </div>

                <div>
                  <label className="block text-xs font-semibold uppercase tracking-wider text-slate-600 mb-1">
                    Question Prompt
                  </label>
                  <textarea
                    value={newText}
                    onChange={(e) => setNewText(e.target.value)}
                    placeholder="e.g. What were your major blockers this week?"
                    rows={3}
                    className="w-full px-3 py-2 text-xs border border-slate-300 rounded-xl focus:ring-2 focus:ring-indigo-500 focus:outline-none"
                    required
                  />
                </div>

                <button
                  type="submit"
                  disabled={adding}
                  className="w-full py-2.5 bg-indigo-600 hover:bg-indigo-700 text-white rounded-xl text-xs font-semibold flex items-center justify-center gap-2 transition-colors disabled:opacity-50 shadow-sm"
                >
                  <Plus className="w-4 h-4" />
                  {adding ? 'Adding Question...' : 'Add Question'}
                </button>
              </form>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
};
