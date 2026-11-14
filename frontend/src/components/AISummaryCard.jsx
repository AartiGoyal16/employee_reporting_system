import React from 'react';
import { Sparkles, CheckCircle2, AlertTriangle, Lightbulb, Bot } from 'lucide-react';

export const AISummaryCard = ({ aiSummary }) => {
  if (!aiSummary) return null;

  const {
    executive_summary,
    key_highlights = [],
    blockers_identified = [],
    manager_recommendation,
    model_used = 'Google Gemini 1.5 Flash',
    generated_at
  } = aiSummary;

  return (
    <div className="bg-gradient-to-br from-indigo-900 via-slate-900 to-blue-950 text-white rounded-2xl p-6 shadow-xl border border-indigo-700/40 relative overflow-hidden">
      {/* Background ambient decorative glow */}
      <div className="absolute -top-16 -right-16 w-48 h-48 bg-blue-500/10 rounded-full blur-2xl pointer-events-none"></div>
      <div className="absolute -bottom-16 -left-16 w-48 h-48 bg-purple-500/10 rounded-full blur-2xl pointer-events-none"></div>

      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3 pb-4 border-b border-white/10 mb-5">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg bg-gradient-to-tr from-amber-400 to-indigo-400 flex items-center justify-center text-slate-950 font-bold shadow-md shadow-amber-400/20">
            <Sparkles className="w-4 h-4" />
          </div>
          <div>
            <h4 className="font-bold text-white text-base tracking-tight flex items-center gap-2">
              AI-Generated Executive Summary
            </h4>
            <p className="text-xs text-indigo-200/70">
              Synthesized from daily updates and weekly reflection questions
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2 bg-white/10 border border-white/15 px-3 py-1 rounded-full text-xs font-medium text-indigo-200">
          <Bot className="w-3.5 h-3.5 text-indigo-300" />
          <span>{model_used}</span>
        </div>
      </div>

      {/* Executive Overview */}
      <div className="mb-5">
        <h5 className="text-xs font-semibold uppercase tracking-wider text-indigo-300 mb-2">
          Executive Overview
        </h5>
        <p className="text-sm text-slate-200 leading-relaxed bg-white/5 p-3.5 rounded-xl border border-white/5">
          {executive_summary}
        </p>
      </div>

      {/* Highlights & Blockers Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-5">
        {/* Key Highlights */}
        <div className="bg-white/5 rounded-xl p-4 border border-white/5">
          <h5 className="text-xs font-semibold uppercase tracking-wider text-emerald-300 mb-2.5 flex items-center gap-1.5">
            <CheckCircle2 className="w-4 h-4 text-emerald-400" /> Key Accomplishments
          </h5>
          <ul className="space-y-2">
            {key_highlights.map((h, idx) => (
              <li key={idx} className="text-xs text-slate-200 flex items-start gap-2">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 mt-1.5 shrink-0"></span>
                <span>{h}</span>
              </li>
            ))}
          </ul>
        </div>

        {/* Blockers & Challenges */}
        <div className="bg-white/5 rounded-xl p-4 border border-white/5">
          <h5 className="text-xs font-semibold uppercase tracking-wider text-amber-300 mb-2.5 flex items-center gap-1.5">
            <AlertTriangle className="w-4 h-4 text-amber-400" /> Blockers & Challenges
          </h5>
          <ul className="space-y-2">
            {blockers_identified.map((b, idx) => (
              <li key={idx} className="text-xs text-slate-200 flex items-start gap-2">
                <span className="w-1.5 h-1.5 rounded-full bg-amber-400 mt-1.5 shrink-0"></span>
                <span>{b}</span>
              </li>
            ))}
          </ul>
        </div>
      </div>

      {/* Manager Recommendation */}
      {manager_recommendation && (
        <div className="bg-gradient-to-r from-blue-600/20 to-indigo-600/20 border border-blue-400/30 rounded-xl p-4 flex items-start gap-3">
          <Lightbulb className="w-5 h-5 text-amber-300 shrink-0 mt-0.5" />
          <div>
            <h5 className="text-xs font-semibold uppercase tracking-wider text-blue-200 mb-1">
              Actionable Manager Recommendation
            </h5>
            <p className="text-xs text-slate-100 leading-relaxed">
              {manager_recommendation}
            </p>
          </div>
        </div>
      )}

      {generated_at && (
        <div className="text-right mt-3 text-[10px] text-indigo-300/50">
          Generated: {new Date(generated_at).toLocaleString()}
        </div>
      )}
    </div>
  );
};
