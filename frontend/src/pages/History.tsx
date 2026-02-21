import React, { useEffect, useState } from 'react';
import { useLanguage } from '../contexts/LanguageContext';

interface Heat {
  heat_id: string;
  furnace_id: string;
  timestamp: string;
  l2_final_temp: number;
  actual_final_temp: number;
  advice_adopted: boolean;
  actual_analysis: Record<string, number>;
}

const History: React.FC = () => {
  const { t } = useLanguage();
  const [heats, setHeats] = useState<Heat[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch('http://localhost:8000/api/heats')
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
                <td className="px-6 py-4">{heat.actual_analysis?.V?.toFixed(3)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};

export default History;
