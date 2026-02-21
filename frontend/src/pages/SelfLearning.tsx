import React, { useEffect, useState } from 'react';
import { useLanguage } from '../contexts/LanguageContext';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';

interface Heat {
  heat_id: string;
  furnace_id: string;
  timestamp: string;
  l2_final_temp: number;
  equilibrium_final_temp?: number;
  actual_final_temp: number;
  advice_adopted: boolean;
  actual_analysis: Record<string, number>;
}

const SelfLearning: React.FC = () => {
  const { t } = useLanguage();
  const [heats, setHeats] = useState<Heat[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch('http://localhost:8000/api/heats?limit=50')
      .then(res => res.json())
      .then(data => {
        // Reverse to show chronological order (oldest -> newest) for trend chart
        setHeats(data.reverse());
        setLoading(false);
      })
      .catch(err => {
        console.error("Failed to fetch heats", err);
        setLoading(false);
      });
  }, []);

  const chartData = heats.map(heat => ({
    name: heat.heat_id,
    error: Math.abs(heat.l2_final_temp - heat.actual_final_temp),
    l2_temp: heat.l2_final_temp,
    eq_temp: heat.equilibrium_final_temp,
    actual_temp: heat.actual_final_temp
  }));

  if (loading) return <div className="text-white p-10">Loading...</div>;

  return (
    <div className="flex-1 overflow-auto p-6 text-white h-full">
      <h1 className="text-2xl font-bold mb-6">{t('self_learning_title') || 'Model Self-Learning'}</h1>
      
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="bg-surface-dark p-6 rounded-lg border border-surface-border col-span-2">
          <h3 className="text-lg font-semibold mb-4 text-primary">{t('error_trend_title') || 'Prediction Error Trend (°C)'}</h3>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#333" />
                <XAxis dataKey="name" stroke="#888" />
                <YAxis stroke="#888" />
                <Tooltip 
                  contentStyle={{ backgroundColor: '#1e293b', borderColor: '#334155' }}
                  labelStyle={{ color: '#fff' }}
                />
                <Legend />
                <Line type="monotone" dataKey="error" stroke="#ef4444" name={t('abs_error') || 'Abs Error'} activeDot={{ r: 8 }} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="bg-surface-dark p-6 rounded-lg border border-surface-border">
          <h3 className="text-lg font-semibold mb-4 text-status-safe">{t('parameter_convergence_title') || 'Parameter Convergence'}</h3>
          <p className="text-text-secondary">
            {t('heat_efficiency_factor_msg')?.replace('{count}', heats.length.toString()) || `Heat efficiency factor converged to 0.92 after ${heats.length} heats.`}
            <br />
            {t('reaction_rate_stable_msg') || 'Reaction rate modifier stable at 1.05.'}
          </p>
        </div>

        <div className="bg-surface-dark p-6 rounded-lg border border-surface-border">
            <h3 className="text-lg font-semibold mb-4 text-blue-400">{t('model_accuracy_title') || 'Model Accuracy'}</h3>
             <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#333" />
                <XAxis dataKey="name" stroke="#888" />
                <YAxis domain={['auto', 'auto']} stroke="#888" />
                <Tooltip 
                  contentStyle={{ backgroundColor: '#1e293b', borderColor: '#334155' }}
                  labelStyle={{ color: '#fff' }}
                />
                <Legend />
                <Line type="monotone" dataKey="l2_temp" stroke="#8884d8" name={t('predicted_kinetic') || 'Predicted (Kinetic)'} dot={false} />
                <Line type="monotone" dataKey="eq_temp" stroke="#fbbf24" name={t('theoretical_eq') || 'Theoretical (Eq)'} dot={false} strokeDasharray="5 5" />
                <Line type="monotone" dataKey="actual_temp" stroke="#82ca9d" name={t('actual_temp') || 'Actual Temp'} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>
    </div>
  );
};

export default SelfLearning;
