import React, { useEffect, useState } from 'react';
import { useLanguage } from '../contexts/LanguageContext';

interface Heat {
  heat_id: string;
  furnace_id: string;
  timestamp: string;
  l2_final_temp: number;
  actual_final_temp: number;
  advice_adopted: boolean;
  trace_id?: string | null;
  advice_message?: string | null;
  advice_reply?: string | null;
  advice_time?: string | null;
  actual_analysis: Record<string, number>;
}

interface AdviceLog {
  trace_id?: string | null;
  message: string;
  reply: string;
  created_at: string;
}

const History: React.FC = () => {
  const { t } = useLanguage();
  const [heats, setHeats] = useState<Heat[]>([]);
  const [loading, setLoading] = useState(true);
  const [adviceLogs, setAdviceLogs] = useState<AdviceLog[]>([]);
  const [adviceLoading, setAdviceLoading] = useState(true);

  useEffect(() => {
    fetch('/api/heats')
      .then(res => res.json())
      .then(data => {
        setHeats(data);
        setLoading(false);
      })
      .catch(err => {
        console.error("Failed to fetch heats", err);
        setLoading(false);
      });
  }, []);

  useEffect(() => {
    fetch('/api/advice')
      .then(res => res.json())
      .then(data => {
        setAdviceLogs(Array.isArray(data) ? data : []);
        setAdviceLoading(false);
      })
      .catch(err => {
        console.error("Failed to fetch advice logs", err);
        setAdviceLoading(false);
      });
  }, []);

  if (loading) return <div className="text-white p-10">Loading...</div>;

  return (
    <div className="flex-1 overflow-auto p-6 text-white h-full">
      <h1 className="text-2xl font-bold mb-6">{t('history_title') || 'Historical Heats'}</h1>
      <div className="overflow-x-auto bg-surface-dark rounded-lg border border-surface-border">
        <table className="w-full text-left text-sm">
          <thead className="bg-surface-border/20 text-text-secondary uppercase">
            <tr>
              <th className="px-6 py-3">{t('timestamp') || 'Timestamp'}</th>
              <th className="px-6 py-3">{t('heat_id') || 'Heat ID'}</th>
              <th className="px-6 py-3">{t('furnace') || 'Furnace'}</th>
              <th className="px-6 py-3">{t('l2_temp_table') || 'L2 Temp (°C)'}</th>
              <th className="px-6 py-3">{t('actual_temp_table') || 'Actual Temp (°C)'}</th>
              <th className="px-6 py-3">{t('adopted_advice') || 'Adopted Advice'}</th>
              <th className="px-6 py-3">{t('trace_id') || 'Trace ID'}</th>
              <th className="px-6 py-3">{t('advice_message') || 'User Message'}</th>
              <th className="px-6 py-3">{t('advice_reply') || 'AI Reply'}</th>
              <th className="px-6 py-3">{t('v_percent') || 'V (%)'}</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-surface-border/50">
            {heats.map((heat) => (
              <tr key={heat.heat_id} className="hover:bg-white/5 transition-colors">
                <td className="px-6 py-4">{new Date(heat.timestamp).toLocaleString()}</td>
                <td className="px-6 py-4 font-mono">{heat.heat_id}</td>
                <td className="px-6 py-4">{heat.furnace_id}</td>
                <td className="px-6 py-4">{heat.l2_final_temp}</td>
                <td className="px-6 py-4">{heat.actual_final_temp}</td>
                <td className="px-6 py-4">
                  <span className={`px-2 py-1 rounded text-xs font-bold ${heat.advice_adopted ? 'bg-status-safe/20 text-status-safe' : 'bg-status-alarm/20 text-status-alarm'}`}>
                    {heat.advice_adopted ? (t('yes') || 'YES') : (t('no') || 'NO')}
                  </span>
                </td>
                <td className="px-6 py-4 font-mono text-[11px]">{heat.trace_id || '--'}</td>
                <td className="px-6 py-4 max-w-[220px] truncate">{heat.advice_message || '--'}</td>
                <td className="px-6 py-4 max-w-[320px] truncate">{heat.advice_reply || '--'}</td>
                <td className="px-6 py-4">{heat.actual_analysis?.V?.toFixed(3)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <h2 className="text-xl font-bold mt-8 mb-4">{t('advice_log_title') || 'AI Advice Logs'}</h2>
      {adviceLoading ? (
        <div className="text-white/70">Loading...</div>
      ) : (
        <div className="overflow-x-auto bg-surface-dark rounded-lg border border-surface-border">
          <table className="w-full text-left text-sm">
            <thead className="bg-surface-border/20 text-text-secondary uppercase">
              <tr>
                <th className="px-6 py-3">{t('advice_time') || 'Time'}</th>
                <th className="px-6 py-3">{t('advice_message') || 'User Message'}</th>
                <th className="px-6 py-3">{t('advice_reply') || 'AI Reply'}</th>
                <th className="px-6 py-3">{t('trace_id') || 'Trace ID'}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-surface-border/50">
              {adviceLogs.map((log, index) => (
                <tr key={`${log.trace_id ?? 'trace'}-${index}`} className="hover:bg-white/5 transition-colors">
                  <td className="px-6 py-4">{new Date(log.created_at).toLocaleString()}</td>
                  <td className="px-6 py-4 max-w-[240px] truncate">{log.message}</td>
                  <td className="px-6 py-4 max-w-[360px] truncate">{log.reply}</td>
                  <td className="px-6 py-4 font-mono text-[11px]">{log.trace_id || '--'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};

export default History;
