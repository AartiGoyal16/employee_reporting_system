import React, { useState, useEffect } from 'react';
import { X, Plus, Check, Settings, AlertCircle } from 'lucide-react';
import { questionService } from '../services/api';

export const QuestionConfigModal = ({ isOpen, onClose }) => {
  const [questions, setQuestions] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [newKey, setNewKey] = useState('');
  const [newText, setNewText] = useState('');
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (isOpen) {
      loadQuestions();
    }
  }, [isOpen]);

  const loadQuestions = async () => {
    setLoading(true);
    setError('');
    try {
      const res = await questionService.getQuestions();
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
    setSaving(true);
    try {
      await questionService.createQuestion({
        key: newKey.trim().toLowerCase().replace(/\s+/g, '_'),
        question_text: newText.trim(),
        order: questions.length + 1,
        is_active: true
      });
      setNewKey('');
      setNewText('');
      await loadQuestions();
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to add question');
    } finally {
      setSaving(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto bg-slate-900/60 backdrop-blur-sm flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl max-w-xl w-full shadow-2xl border border-slate-100 overflow-hidden">
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100 bg-slate-50/70">
          <div className="flex items-center gap-2">
            <Settings className="w-5 h-5 text-indigo-600" />
            <h3 className="font-semibold text-slate-900 text-lg">Manage Weekly Questions</h3>
          </div>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600 p-1.5 rounded-lg">
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="p-6 space-y-5">
          {error && (
            <div className="p-3 bg-red-50 border border-red-200 rounded-xl text-xs text-red-700 flex items-center gap-2">
              <AlertCircle className="w-4 h-4 shrink-0" />
              <span>{error}</span>
            </div>
          )}

          {/* Current Questions List */}
          <div>
            <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-500 mb-2">
              Active Reporting Questions ({questions.length})
            </h4>
            <div className="space-y-2 max-h-56 overflow-y-auto pr-1">
              {questions.map((q, idx) => (
                <div key={q.id || idx} className="p-3 bg-slate-50 rounded-xl border border-slate-200 flex items-start gap-3">
                  <span className="w-5 h-5 rounded-full bg-indigo-100 text-indigo-700 font-bold text-xs flex items-center justify-center shrink-0 mt-0.5">
                    {idx + 1}
                  </span>
                  <div className="flex-1">
                    <p className="text-xs font-semibold text-slate-800">{q.question_text}</p>
                    <span className="text-[10px] text-slate-400 font-mono">key: {q.key}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Add New Question Form */}
          <form onSubmit={handleAddQuestion} className="pt-4 border-t border-slate-100 space-y-3">
            <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-500">
              Add Custom Question
            </h4>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              <input
                type="text"
                placeholder="Key (e.g. blockers)"
                value={newKey}
                onChange={(e) => setNewKey(e.target.value)}
                className="px-3 py-2 text-xs border border-slate-200 rounded-xl focus:ring-2 focus:ring-indigo-500 focus:outline-none"
                required
              />
              <input
                type="text"
                placeholder="Full Question Prompt"
                value={newText}
                onChange={(e) => setNewText(e.target.value)}
                className="sm:col-span-2 px-3 py-2 text-xs border border-slate-200 rounded-xl focus:ring-2 focus:ring-indigo-500 focus:outline-none"
                required
              />
            </div>
            <button
              type="submit"
              disabled={saving}
              className="w-full py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-xl text-xs font-medium flex items-center justify-center gap-1.5 transition-colors disabled:opacity-50"
            >
              <Plus className="w-4 h-4" />
              {saving ? 'Adding...' : 'Add Question'}
            </button>
          </form>
        </div>
      </div>
    </div>
  );
};
