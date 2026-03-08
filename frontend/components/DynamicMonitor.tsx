import React, { useState, useEffect } from 'react';
import {
  ComposedChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
  Scatter
} from 'recharts';
import { useProcessStream } from '../src/hooks/useProcessStream';
import { useLanguage } from '../src/contexts/LanguageContext';

interface ChartDataPoint {
  time: number;
  poolTemp: number;
  si: number;
  v: number;
  c: number;
  isTempEstimated: boolean;
  sample?: {
    time: number;
    temp: number;
    C: number;
    V: number;
  };
}

interface ApprovalModalProps {
  threadId: string;
  message: string;
  onApprove: () => void;
  onModify: (recipe: any) => void;
  loading?: boolean;
}

const ApprovalModal: React.FC<ApprovalModalProps> = ({ threadId, message, onApprove, onModify, loading }) => {
  const [showModify, setShowModify] = useState(false);
  const [scaleAdd, setScaleAdd] = useState(1.0);

  return (
    <div className="fixed inset-0 bg-black/70 backdrop-blur-sm z-50 flex items-center justify-center">
      <div className="bg-gray-900 border border-red-500/50 rounded-xl p-6 max-w-md w-full shadow-2xl animate-in fade-in zoom-in duration-200">
        <div className="flex items-center gap-3 mb-4 text-red-400">
          <span className="material-symbols-outlined text-3xl">warning</span>
          <h2 className="text-xl font-bold">需要人工审批 (Human-in-the-loop)</h2>
        </div>
        
        <p className="text-gray-300 mb-6 bg-red-500/10 p-3 rounded border border-red-500/20">
          {message || "系统检测到关键工艺偏差（温度或收得率），请确认是否继续。"}
        </p>

        {loading ? (
           <div className="flex flex-col items-center justify-center py-4 space-y-3">
             <div className="w-8 h-8 border-4 border-blue-500 border-t-transparent rounded-full animate-spin"></div>
             <p className="text-blue-400 text-sm font-bold animate-pulse">正在重新计算仿真结果，请稍候...</p>
           </div>
        ) : !showModify ? (
          <div className="flex gap-3 justify-end">
            <button 
              onClick={() => setShowModify(true)}
              className="px-4 py-2 rounded bg-gray-800 hover:bg-gray-700 text-gray-300 border border-gray-600 transition-colors"
            >
              🛠️ 修改参数
            </button>
            <button 
              onClick={onApprove}
              className="px-4 py-2 rounded bg-red-600 hover:bg-red-500 text-white font-bold shadow-lg shadow-red-900/50 transition-all flex items-center gap-2"
            >
              <span>✅</span>
              <span>批准继续</span>
            </button>
          </div>
        ) : (
          <div className="space-y-4">
            <div className="bg-gray-800 p-3 rounded">
               <label className="text-sm text-gray-400 block mb-1">追加氧化铁皮 (吨)</label>
               <input 
                 type="number" 
                 value={scaleAdd} 
                 onChange={e => setScaleAdd(parseFloat(e.target.value))}
                 className="w-full bg-gray-900 border border-gray-700 rounded p-2 text-white"
                 step="0.1"
               />
            </div>
            <div className="flex gap-3 justify-end">
               <button 
                 onClick={() => setShowModify(false)}
                 className="text-gray-400 hover:text-white text-sm"
               >
                 取消
               </button>
               <button 
                 onClick={() => onModify({ scale_weight: scaleAdd })}
                 className="px-4 py-2 rounded bg-blue-600 hover:bg-blue-500 text-white font-bold"
               >
                 🚀 提交修正并重算
               </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

const DynamicMonitor: React.FC = () => {
  const { data, isConnected } = useProcessStream();
  const { t } = useLanguage();
  const [chartData, setChartData] = useState<ChartDataPoint[]>([]);
  
  // Graph State Polling
  const [interruptState, setInterruptState] = useState<any>(null);
  const [isGraphLoading, setIsGraphLoading] = useState(false);
  
  // Poll for graph interrupt state (Mocking real websocket/polling for demo)
  // In real app, this would check /api/graph/status or similar
  // Here we just simulate it occasionally or wait for a specific trigger if we had one.
  // For now, let's assume we might receive a specific event in the stream data 
  // or we could poll a new endpoint if we created one.
  // Since we didn't create a status polling endpoint, we rely on the `run` response.
  // But `run` is async.
  // Let's assume the Dashboard might trigger a run.
  
  // For demonstration of the UI, let's add a hidden trigger or just check if data contains an interrupt flag.
  // Let's modify the chart data update to check for a special flag if we added one.
  // Or better, let's add a manual "Start New Heat" button that calls the graph API.

  const handleGraphRun = async () => {
      setIsGraphLoading(true);
      try {
          const res = await fetch('/api/graph/run', {
              method: 'POST',
              headers: {'Content-Type': 'application/json'},
              body: JSON.stringify({
                  si: 0.20,
                  temp: 1350,
                  is_one_can: true
              })
          });
          const result = await res.json();
          if (result.status === 'interrupted') {
              setInterruptState(result);
          }
      } catch (e) {
          console.error(e);
      } finally {
          setIsGraphLoading(false);
      }
  };
  
  const handleApprove = async () => {
      if (!interruptState) return;
      setIsGraphLoading(true);
      try {
          const res = await fetch('/api/graph/approve', {
              method: 'POST',
              headers: {'Content-Type': 'application/json'},
              body: JSON.stringify({
                  thread_id: interruptState.thread_id,
                  action: 'approve'
              })
          });
          
          if (!res.ok) {
              const err = await res.json();
              alert(`错误: ${err.detail || '请求失败'}`);
              setInterruptState(null); // Close modal on error to prevent stuck state
              return;
          }

          const result = await res.json();
          if (result.status === 'completed') {
              setInterruptState(null);
              // Maybe refresh data or show success
          } else if (result.status === 'interrupted') {
              setInterruptState(result); // Recursive interrupt?
          }
      } catch (e) { 
          console.error(e); 
          alert("网络请求失败，请检查后端连接。");
          setInterruptState(null);
      } finally {
          setIsGraphLoading(false);
      }
  };

  const handleModify = async (recipe: any) => {
      if (!interruptState) return;
      setIsGraphLoading(true);
      try {
          const res = await fetch('/api/graph/approve', {
              method: 'POST',
              headers: {'Content-Type': 'application/json'},
              body: JSON.stringify({
                  thread_id: interruptState.thread_id,
                  action: 'modify',
                  recipe: recipe
              })
          });

          if (!res.ok) {
              const err = await res.json();
              alert(`错误: ${err.detail || '请求失败'}`);
              setInterruptState(null);
              return;
          }

          const result = await res.json();
          if (result.status === 'completed') {
              setInterruptState(null);
          } else if (result.status === 'interrupted') {
              setInterruptState(result);
          }
      } catch (e) { 
          console.error(e);
          alert("网络请求失败，请检查后端连接。");
          setInterruptState(null);
      } finally {
          setIsGraphLoading(false);
      }
  };

  // Fetch history on mount
  useEffect(() => {
    const fetchHistory = async () => {
      try {
        const res = await fetch('/api/simulation/history');
        const json = await res.json();
        if (json.history && Array.isArray(json.history)) {
          const historyPoints = json.history.map((d: any) => ({
            time: d.process_time,
            poolTemp: d.temperature?.value,
            si: d.chemistry?.si ?? 0,
            v: d.chemistry?.v ?? 0,
            c: d.chemistry?.c ?? 0,
            isTempEstimated: !d.temperature?.status?.is_valid,
            sample: d.latest_sample
          }));
          
          setChartData(prev => {
             const combined = [...historyPoints, ...prev];
             // Deduplicate by time
             const unique = combined.filter((v, i, a) => a.findIndex(t => t.time === v.time) === i);
             return unique.slice(-600); // Keep last 10 mins (600 points)
           });
        }
      } catch (err) {
        console.error("Failed to fetch history:", err);
      }
    };
    
    fetchHistory();
  }, []);

  // Handle incoming stream data
  useEffect(() => {
    if (data?.process_time !== undefined && data?.temperature?.value !== undefined) {
      setChartData(prev => {
        // Use process_time from backend directly to ensure sync
        const time = data.process_time!;
        
        // Avoid duplicate points for same time
        if (prev.length > 0 && prev[prev.length - 1].time === time) {
          return prev;
        }

        const newData = [...prev, {
          time,
          poolTemp: data.temperature!.value,
          si: data.chemistry?.si ?? 0,
          v: data.chemistry?.v ?? 0,
          c: data.chemistry?.c ?? 0,
          isTempEstimated: !data.temperature!.status.is_valid,
          sample: data.latest_sample // Pass sample data if available
        }];
        
        // Keep last 600 points
        return newData.slice(-600);
      });
    } else if (!isConnected) {
      // Optional: Clear or keep stale data on disconnect? 
      // Keeping stale data is usually better for UX.
    }
  }, [data, isConnected]);

  const tempStatus = data?.temperature?.status;
  const isSensorFault = tempStatus && !tempStatus.is_valid;
  const processTime = data?.process_time;
  const phaseKey = processTime === undefined ? null : processTime < 0.5 ? 'phase_ignition' : processTime < 5.5 ? 'phase_main_blow' : 'phase_end_pressing';
  const phaseLabel = phaseKey ? t(phaseKey as any) : '--';
  const tempValue = data?.temperature?.value;
  const tempLevel = tempValue === undefined ? null : tempValue >= 1400 ? 'critical' : tempValue >= 1360 ? 'warning' : 'normal';
  const tempStatusLabel = tempLevel ? t(`temp_status_${tempLevel}` as any) : '--';
  const tempStatusClass = tempLevel === 'critical'
    ? 'bg-status-alarm/20 border-status-alarm/40 text-status-alarm'
    : tempLevel === 'warning'
      ? 'bg-status-warning/20 border-status-warning/40 text-status-warning'
      : 'bg-status-safe/20 border-status-safe/40 text-status-safe';

  return (
    <div className="flex flex-col gap-1 min-h-[320px] flex-1">
      <div className="flex items-center justify-between mb-1 pl-1">
        <div className="flex items-center gap-2">
          <span className="material-symbols-outlined text-status-warning text-xl">query_stats</span>
          <h1 className="text-white text-base font-bold tracking-wide">{t('dynamic_monitor_title')}</h1>
          {/* Debug Button for Interrupt */}
          <button 
             onClick={handleGraphRun}
             className="text-[10px] bg-blue-500/20 text-blue-300 border border-blue-500/40 px-2 py-0.5 rounded hover:bg-blue-500/40"
             title="Start a test graph run to trigger potential interrupt"
          >
             Run Graph (Debug)
          </button>
        </div>
        <div className="flex items-center gap-2">
          <div className="flex items-center gap-2 px-2 py-1 rounded border bg-surface-dark/80 border-surface-border">
            <span className="text-[10px] font-mono font-bold text-text-secondary uppercase tracking-wider">{t('phase_label')}</span>
            <span className="text-[10px] font-bold text-white">{phaseLabel}</span>
            <span className="text-[10px] text-text-secondary font-mono">{typeof processTime === 'number' ? `${processTime.toFixed(2)}${t('min_short')}` : '--'}</span>
          </div>
          <div className={`flex items-center gap-2 px-2 py-1 rounded border ${tempStatusClass}`}>
            <span className="text-[10px] font-mono font-bold uppercase tracking-wider">{t('temp_status')}</span>
            <span className="text-[10px] font-bold">{tempStatusLabel}</span>
          </div>
          {isSensorFault && (
             <div className="flex items-center gap-1 bg-status-alarm/20 px-2 py-1 rounded border border-status-alarm/40 animate-pulse">
               <span className="material-symbols-outlined text-status-alarm text-xs">warning</span>
               <span className="text-[10px] font-bold text-status-alarm uppercase">{t('sensor_fault')}</span>
             </div>
          )}
          <div className={`flex items-center gap-2 px-2 py-1 rounded border transition-colors ${isConnected ? 'bg-status-alarm/10 border-status-alarm/20' : 'bg-gray-500/10 border-gray-500/20'}`}>
            <span className={`flex h-1.5 w-1.5 rounded-full ${isConnected ? 'bg-status-alarm animate-pulse' : 'bg-gray-500'}`}></span>
            <span className={`text-[10px] font-mono font-bold uppercase tracking-wider ${isConnected ? 'text-status-alarm' : 'text-gray-500'}`}>
              {isConnected ? t('live_data') : t('offline')}
            </span>
          </div>
        </div>
      </div>
      <div className="glass-panel rounded-xl p-1 flex-1 flex flex-col shadow-lg relative overflow-hidden group">
        <div className="flex items-center justify-between px-3 pt-3">
          <div className={`backdrop-blur-md px-3 py-1.5 rounded shadow-lg transition-colors duration-300 ${isSensorFault ? 'bg-status-warning/10' : 'bg-surface-dark/90'}`}>
            <span className="text-[10px] text-text-secondary uppercase font-bold mr-2 tracking-wider">{t('temp_pool')}</span>
            <span className={`text-xl font-mono font-bold ${isSensorFault ? 'text-status-warning' : 'text-white'}`}>
              {data?.temperature?.value?.toFixed(0) ?? '--'}
              <span className="text-sm text-text-secondary ml-1">°C</span>
            </span>
            {isSensorFault && <div className="text-[9px] text-status-warning font-bold text-right mt-[-2px]">{t('confidence')}: {(tempStatus!.confidence * 100).toFixed(0)}%</div>}
          </div>
          <div className="bg-surface-dark/90 backdrop-blur-md px-3 py-1.5 rounded shadow-lg">
            <span className="text-[10px] text-text-secondary uppercase font-bold mr-2 tracking-wider">{t('v_content')}</span>
            <span className="text-xl font-mono font-bold text-primary">
              {data?.chemistry?.v?.toFixed(3) ?? '--'}
              <span className="text-sm text-text-secondary ml-1">%</span>
            </span>
          </div>
        </div>
        
        {/* Chart Area */}
        <div className="w-full h-full relative bg-[#0b1116] rounded-lg border border-white/5 flex-1 min-h-[250px] p-2 pt-3">
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={chartData} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#2A3848" strokeOpacity={0.4} />
              <XAxis 
                dataKey="time" 
                type="number" 
                domain={[0, 8]} 
                ticks={[0, 1, 2, 3, 4, 5, 6, 7, 8]}
                stroke="#9dabb9" 
                fontSize={12} 
                tickFormatter={(val) => `${val}${t('min_short')}`}
              />
              <YAxis 
                yAxisId="temp" 
                domain={[1200, 1550]} 
                tickCount={8}
                stroke="#e2e8f0" 
                fontSize={12} 
                width={50}
                label={{ value: t('temp_axis'), angle: -90, position: 'insideLeft', fill: '#e2e8f0', fontSize: 12, dx: 10 }}
              />
              <YAxis 
                yAxisId="chem" 
                orientation="right" 
                domain={[0, 4.0]} 
                tickCount={5}
                stroke="#137fec" 
                fontSize={12} 
                width={50}
                label={{ value: t('content_axis'), angle: 90, position: 'insideRight', fill: '#137fec', fontSize: 12, dx: -10 }}
              />
              <Tooltip 
                content={({ active, payload, label }) => {
                  if (active && payload && payload.length) {
                    return (
                      <div className="bg-[#1A2634] border border-[#2A3848] rounded-lg p-2 text-sm shadow-xl">
                        <div className="text-gray-400 text-xs mb-1 font-mono">
                          {t('time_label')}: {typeof label === 'number' ? label.toFixed(2) : label} {t('min_unit')}
                        </div>
                        {payload.map((entry: any, index: number) => {
                           // Skip redundant 'time' entries or non-data keys
                           if (entry.dataKey === 'time' || !entry.name) return null;
                           // Special formatting for different types
                           const isTemp = entry.dataKey === 'poolTemp' || entry.dataKey === 'temp';
                           const isSample = entry.name === t('legend_sample');
                           const value = typeof entry.value === 'number' ? entry.value.toFixed(isTemp ? 1 : 3) : entry.value;
                           
                           return (
                             <div key={index} className="flex items-center gap-2 py-0.5">
                               <div className="w-2 h-2 rounded-full" style={{ backgroundColor: entry.color }}></div>
                               <span className="text-gray-300">{entry.name}:</span>
                               <span className="font-mono font-bold" style={{ color: entry.color }}>{value}</span>
                               {isSample && <span className="text-xs text-gray-500 ml-1">({t('sample_note')})</span>}
                             </div>
                           );
                        })}
                      </div>
                    );
                  }
                  return null;
                }}
              />
              <ReferenceLine y={1360} yAxisId="temp" stroke="#ef4444" strokeDasharray="5 5" label={{ value: t('crit_temp'), position: 'insideTopRight', fill: '#ef4444', fontSize: 12 }} />
              
              <Line yAxisId="temp" type="monotone" dataKey="poolTemp" stroke={isSensorFault ? "#f59e0b" : "#e2e8f0"} strokeWidth={3} dot={false} isAnimationActive={false} name={t('legend_temp')} />
              <Line yAxisId="chem" type="monotone" dataKey="c" stroke="#22c55e" strokeWidth={2} strokeDasharray="3 3" dot={false} isAnimationActive={false} name={t('legend_c')} />
              <Line yAxisId="chem" type="monotone" dataKey="si" stroke="#a855f7" strokeWidth={2} strokeDasharray="3 3" dot={false} isAnimationActive={false} name={t('legend_si')} />
              <Line yAxisId="chem" type="monotone" dataKey="v" stroke="#137fec" strokeWidth={3} dot={false} isAnimationActive={false} name={t('legend_v')} />
              
              <Scatter 
                yAxisId="temp" 
                data={chartData
                  .filter(d => d.sample && Math.abs(d.time - d.sample.time) < 0.05)
                  .map(d => ({ time: d.sample!.time, temp: d.sample!.temp }))} 
                dataKey="temp" 
                name={t('legend_sample')} 
                shape={<circle r={6} fill="#ef4444" stroke="#fff" strokeWidth={2} />}
              />

              <ReferenceLine x={data?.process_time} stroke="#f59e0b" strokeWidth={1} />
            </ComposedChart>
          </ResponsiveContainer>
        </div>

        <div className="flex justify-between items-center py-2 px-4 border-t border-surface-border bg-surface-dark text-xs font-medium">
           <div className="flex gap-4">
              <div className="flex items-center gap-2">
                <span className="w-3 h-1 bg-white rounded-full"></span>
                <span className="text-text-secondary">{t('legend_temp')}</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="w-2 h-2 bg-status-alarm rounded-full border border-white/50"></span>
                <span className="text-text-secondary">{t('legend_sample')}</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="w-3 h-1 bg-primary rounded-full shadow-neon-blue"></span>
                <span className="text-text-secondary">{t('legend_v')}</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="w-3 h-1 border-b border-dashed border-status-safe"></span>
                <span className="text-text-secondary">{t('legend_c')}</span>
              </div>
           </div>
           
           {/* Model Parameters / Self-Learning Display */}
           {data?.model_params && (
             <div className="flex gap-4 items-center">
               <div className="flex flex-col items-end">
                 <span className="text-[9px] text-text-secondary uppercase">{t('heat_eff_ai')}</span>
                 <span className="text-[10px] font-mono text-primary font-bold">{(data.model_params.heat_efficiency * 100).toFixed(1)}%</span>
               </div>
               <div className="flex flex-col items-end">
                 <span className="text-[9px] text-text-secondary uppercase">{t('reaction_rate_mod')}</span>
                 <span className="text-[10px] font-mono text-primary font-bold">x{data.model_params.reaction_rate_mod.toFixed(2)}</span>
               </div>
             </div>
           )}
        </div>
      </div>
      {interruptState && (
        <ApprovalModal 
           threadId={interruptState.thread_id}
           message={interruptState.messages && interruptState.messages.length > 0 ? interruptState.messages[interruptState.messages.length-1] : "需要人工审批"}
           onApprove={handleApprove}
           onModify={handleModify}
           loading={isGraphLoading}
        />
      )}
    </div>
  );
};

export default DynamicMonitor;
