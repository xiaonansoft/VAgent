import React, { useState, useEffect } from 'react';
import {
  ComposedChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine
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

interface DynamicMonitorProps {
  viewMode?: 'dual' | 'expert' | 'operator';
}

const DynamicMonitor: React.FC<DynamicMonitorProps> = () => {
  const TIME_MATCH_EPSILON_MIN = 0.005;
  const PROCESS_RESET_THRESHOLD_MIN = 1;
  const { data, isConnected } = useProcessStream();
  const { t } = useLanguage();
  const [chartData, setChartData] = useState<ChartDataPoint[]>([]);
  
  useEffect(() => {
    const fetchHistory = async () => {
      try {
        const res = await fetch('/api/simulation/history');
        const json = await res.json();
        if (json.history && Array.isArray(json.history)) {
          const historyPoints = json.history
            .map((d: any) => ({
              time: Number(d.process_time),
              poolTemp: Number(d.temperature?.value),
              si: Number(d.chemistry?.si ?? 0),
              v: Number(d.chemistry?.v ?? 0),
              c: Number(d.chemistry?.c ?? 0),
              isTempEstimated: !d.temperature?.status?.is_valid,
              sample: d.latest_sample
            }))
            .filter((point: ChartDataPoint) => Number.isFinite(point.time) && Number.isFinite(point.poolTemp))
            .sort((a: ChartDataPoint, b: ChartDataPoint) => a.time - b.time);
          const uniqueHistory = historyPoints.filter((point: ChartDataPoint, index: number, arr: ChartDataPoint[]) => {
            if (index === 0) {
              return true;
            }
            return Math.abs(point.time - arr[index - 1].time) > TIME_MATCH_EPSILON_MIN;
          });
          setChartData(uniqueHistory.slice(-600));
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
        const time = Number(data.process_time);
        if (!Number.isFinite(time)) {
          return prev;
        }
        
        const nextPoint: ChartDataPoint = {
          time,
          poolTemp: data.temperature!.value,
          si: data.chemistry?.si ?? 0,
          v: data.chemistry?.v ?? 0,
          c: data.chemistry?.c ?? 0,
          isTempEstimated: !data.temperature!.status.is_valid,
          sample: data.latest_sample
        };

        if (prev.length > 0) {
          const lastPoint = prev[prev.length - 1];
          if (lastPoint.time - time > PROCESS_RESET_THRESHOLD_MIN) {
            return [nextPoint];
          }
        }

        if (prev.length > 0 && Math.abs(prev[prev.length - 1].time - time) <= TIME_MATCH_EPSILON_MIN) {
          const updated = [...prev];
          updated[updated.length - 1] = nextPoint;
          return updated;
        }

        const newData = [...prev, nextPoint];
        
        // Keep last 600 points
        return newData.slice(-600);
      });
    } else if (!isConnected) {
      // Optional: Clear or keep stale data on disconnect? 
      // Keeping stale data is usually better for UX.
    }
  }, [data, isConnected]);

  const processTime = data?.process_time;
  const processTimeLabel = typeof processTime === 'number' ? `${processTime.toFixed(1)}${t('min_short')}` : '--';
  const phaseKey = processTime === undefined ? null : processTime < 0.5 ? 'phase_ignition' : processTime < 5.5 ? 'phase_main_blow' : 'phase_end_pressing';
  const phaseLabel = phaseKey ? t(phaseKey as any) : '--';
  const tempValue = data?.temperature?.value;
  const tempLevel = tempValue === undefined ? null : tempValue >= 1400 ? 'critical' : tempValue >= 1360 ? 'warning' : 'normal';
  const isTempAbnormal = tempLevel === 'warning' || tempLevel === 'critical';
  const criticalTemp = data?.chemistry?.v !== undefined
    ? 1361 + (data.chemistry.v - 0.12) * 80
    : 1361;
  const marginToCritical = typeof tempValue === 'number' ? tempValue - criticalTemp : null;
  const riskLevel = marginToCritical === null
    ? 'low'
    : marginToCritical >= 0
      ? 'high'
      : marginToCritical >= -8
        ? 'medium'
        : 'low';
  const riskClass = riskLevel === 'high'
    ? 'text-status-alarm border-status-alarm/40 bg-status-alarm/10'
    : riskLevel === 'medium'
      ? 'text-status-warning border-status-warning/40 bg-status-warning/10'
      : 'text-status-safe border-status-safe/40 bg-status-safe/10';
  const xAxisDomain = React.useMemo<[number, number]>(() => {
    const tickStep = 0.5;
    const span = 6;
    const rawAnchor = typeof processTime === 'number'
      ? processTime
      : chartData.length > 0
        ? chartData[chartData.length - 1].time
        : 0;
    const anchor = Number.isFinite(rawAnchor) ? Math.max(0, rawAnchor) : 0;
    const end = anchor <= span ? span : Math.ceil(anchor / tickStep) * tickStep;
    const start = Math.max(0, Number((end - span).toFixed(1)));
    return [start, end];
  }, [processTime, chartData]);
  const xAxisTicks = React.useMemo<number[]>(() => {
    const [start, end] = xAxisDomain;
    const ticks: number[] = [];
    for (let v = start; v <= end + 0.0001; v += 0.5) {
      ticks.push(Number(v.toFixed(1)));
    }
    return ticks;
  }, [xAxisDomain]);
  const tempDomain = React.useMemo<[number, number]>(() => {
    const temps = chartData
      .map((point) => point.poolTemp)
      .filter((value) => Number.isFinite(value));
    if (typeof tempValue === 'number' && Number.isFinite(tempValue)) {
      temps.push(tempValue);
    }
    if (temps.length === 0) {
      return [1200, 1550];
    }
    const minTemp = Math.min(...temps);
    const maxTemp = Math.max(...temps);
    const paddedMin = Math.floor((minTemp - 20) / 10) * 10;
    const paddedMax = Math.ceil((maxTemp + 20) / 10) * 10;
    const lower = Math.max(1000, paddedMin);
    const upper = Math.min(2000, Math.max(lower + 80, paddedMax));
    return [lower, upper];
  }, [chartData, tempValue]);
  const vDomain = React.useMemo<[number, number]>(() => {
    const values = chartData
      .map((point) => point.v)
      .filter((value) => Number.isFinite(value));
    if (typeof data?.chemistry?.v === 'number' && Number.isFinite(data.chemistry.v)) {
      values.push(data.chemistry.v);
    }
    if (values.length === 0) {
      return [0, 0.2];
    }
    const minValue = Math.min(...values);
    const maxValue = Math.max(...values);
    const paddedMin = Math.max(0, minValue - 0.004);
    const paddedMax = Math.min(1.2, maxValue + 0.004);
    const span = Math.max(0.03, paddedMax - paddedMin);
    const step = span <= 0.05 ? 0.005 : span <= 0.12 ? 0.01 : 0.02;
    const lower = Math.max(0, Math.floor(paddedMin / step) * step);
    const upper = Math.min(1.2, Math.max(lower + step * 4, Math.ceil(paddedMax / step) * step));
    return [Number(lower.toFixed(3)), Number(upper.toFixed(3))];
  }, [chartData, data?.chemistry?.v]);
  const vAxisTicks = React.useMemo<number[]>(() => {
    const [lower, upper] = vDomain;
    const span = upper - lower;
    const step = span <= 0.05 ? 0.005 : span <= 0.12 ? 0.01 : 0.02;
    const ticks: number[] = [];
    for (let v = lower; v <= upper + 0.00001; v += step) {
      ticks.push(Number(v.toFixed(3)));
    }
    return ticks;
  }, [vDomain]);
  const cDomain = React.useMemo<[number, number]>(() => {
    const values = chartData
      .map((point) => point.c)
      .filter((value) => Number.isFinite(value));
    if (values.length === 0) {
      return [0, 4];
    }
    const minValue = Math.max(0, Math.min(...values) - 0.2);
    const maxValue = Math.min(6, Math.max(...values) + 0.2);
    const lower = Math.floor(minValue * 10) / 10;
    const upper = Math.max(lower + 0.6, Math.ceil(maxValue * 10) / 10);
    return [lower, upper];
  }, [chartData]);

  return (
    <div className="flex flex-col gap-2 min-h-[320px] flex-1">
      <div className="glass-panel rounded-xl p-2 flex-1 flex flex-col shadow-lg relative overflow-hidden group">
        <div className="px-2 py-2 border-b border-surface-border/50 flex items-center justify-between bg-surface-dark/40 rounded-t-lg gap-2">
          <div className="flex items-center gap-2">
            <div className="size-6 bg-primary/20 rounded flex items-center justify-center border border-primary/30">
              <span className="material-symbols-outlined text-primary text-sm animate-pulse">query_stats</span>
            </div>
            <h3 className="text-xs font-bold text-white tracking-widest uppercase">{t('dynamic_monitor_title')}</h3>
          </div>
          <div className="flex items-center justify-end flex-wrap gap-2">
            <div className={`flex items-center gap-2 px-2.5 py-1 rounded-md border ${isTempAbnormal ? 'bg-status-alarm/10 border-status-alarm/40' : 'bg-surface-dark/80 border-surface-border'}`}>
              <span className="text-[10px] font-mono font-bold text-text-secondary uppercase tracking-wider">{t('temp_pool')}</span>
              <span className={`text-[10px] font-mono font-bold ${isTempAbnormal ? 'text-status-alarm' : 'text-white'}`}>
                {data?.temperature?.value?.toFixed(0) ?? '--'}°C
              </span>
            </div>
            <div className="flex items-center gap-2 px-2.5 py-1 rounded-md border bg-surface-dark/80 border-surface-border">
              <span className="text-[10px] font-mono font-bold text-text-secondary uppercase tracking-wider">{t('v_content')}</span>
              <span className="text-[10px] font-mono font-bold text-primary">{data?.chemistry?.v?.toFixed(3) ?? '--'}%</span>
            </div>
            <div className="flex items-center gap-2 px-2.5 py-1 rounded-md border bg-surface-dark/80 border-surface-border">
              <span className="text-[10px] font-mono font-bold text-text-secondary uppercase tracking-wider">{t('phase_label')}</span>
              <span className="text-[10px] font-bold text-white">{phaseLabel}</span>
              <span className="text-[10px] text-text-secondary font-mono">{processTimeLabel}</span>
            </div>
            <div className={`flex items-center gap-2 px-2.5 py-1 rounded-md border ${riskClass}`}>
              <span className="text-[10px] font-mono font-bold uppercase tracking-wider">{t('risk_level')}</span>
              <span className="text-[10px] font-bold">{riskLevel === 'high' ? t('risk_high') : riskLevel === 'medium' ? t('risk_medium') : t('risk_low')}</span>
              <span className="text-[10px] text-text-secondary font-mono">
                {marginToCritical === null ? '--' : `${marginToCritical >= 0 ? '+' : ''}${marginToCritical.toFixed(1)}°C`}
              </span>
            </div>
          </div>
        </div>
        <div className="w-full h-full relative bg-[#0b1116] rounded-lg border border-white/5 flex-1 min-h-[280px] p-2 pt-3 mt-2">
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={chartData} margin={{ top: 18, right: 30, left: 6, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#2A3848" strokeOpacity={0.55} strokeWidth={1.1} />
              <XAxis 
                dataKey="time" 
                type="number" 
                domain={xAxisDomain}
                ticks={xAxisTicks}
                allowDataOverflow
                stroke="#9dabb9" 
                fontSize={12} 
                tickFormatter={(val) => `${Number(val).toFixed(1)}${t('min_short')}`}
              />
              <YAxis 
                yAxisId="temp" 
                domain={tempDomain}
                tickCount={8}
                stroke="#e2e8f0" 
                fontSize={12} 
                width={62}
                label={{ value: t('temp_axis'), angle: -90, position: 'insideLeft', fill: '#e2e8f0', fontSize: 12, dx: 10 }}
              />
              <YAxis 
                yAxisId="vAxis" 
                orientation="right" 
                domain={vDomain}
                ticks={vAxisTicks}
                stroke="#137fec" 
                fontSize={12} 
                width={66}
                tick={{ fill: '#93c5fd' }}
                tickMargin={8}
                tickFormatter={(val) => `${Number(val).toFixed(3)}`}
                label={{ value: `${t('legend_v')} %`, angle: 90, position: 'insideRight', fill: '#137fec', fontSize: 12, dx: -10 }}
              />
              <YAxis yAxisId="cAxis" orientation="right" domain={cDomain} hide />
              <Tooltip 
                content={({ active, payload, label }) => {
                  if (active && payload && payload.length) {
                    return (
                      <div className="bg-[#1A2634] border border-[#2A3848] rounded-lg p-2 text-sm shadow-xl">
                        <div className="text-gray-400 text-xs mb-1 font-mono">
                          {t('time_label')}: {typeof label === 'number' ? label.toFixed(1) : label} {t('min_unit')}
                        </div>
                        {payload.map((entry: any, index: number) => {
                           if (entry.dataKey === 'time' || !entry.name) return null;
                           const isTemp = entry.dataKey === 'poolTemp' || entry.dataKey === 'temp';
                           const value = typeof entry.value === 'number' ? entry.value.toFixed(isTemp ? 1 : 3) : entry.value;
                           
                           return (
                             <div key={index} className="flex items-center gap-2 py-0.5">
                               <div className="w-2 h-2 rounded-full" style={{ backgroundColor: entry.color }}></div>
                               <span className="text-gray-300">{entry.name}:</span>
                               <span className="font-mono font-bold" style={{ color: entry.color }}>{value}</span>
                             </div>
                           );
                        })}
                      </div>
                    );
                  }
                  return null;
                }}
              />
              <Line yAxisId="temp" type="monotone" dataKey="poolTemp" stroke="#e2e8f0" strokeWidth={3} dot={chartData.length <= 1 ? { r: 3, fill: '#e2e8f0' } : false} isAnimationActive={false} name={t('legend_temp')} />
              <Line yAxisId="cAxis" type="monotone" dataKey="c" stroke="#22c55e" strokeWidth={2} strokeDasharray="3 3" dot={false} isAnimationActive={false} name={t('legend_c')} />
              <Line yAxisId="vAxis" type="monotone" dataKey="v" stroke="#137fec" strokeWidth={3} dot={false} isAnimationActive={false} name={t('legend_v')} />
              {typeof processTime === 'number' && (
                <ReferenceLine x={processTime} stroke="#f59e0b" strokeWidth={1.5} />
              )}
            </ComposedChart>
          </ResponsiveContainer>
        </div>

        <div className="flex flex-wrap justify-between items-center gap-y-2 py-2 px-4 border-t border-surface-border bg-surface-dark text-xs font-medium">
           <div className="flex flex-wrap gap-4">
              <div className="flex items-center gap-2">
                <span className="w-3 h-1 bg-white rounded-full"></span>
                <span className="text-text-secondary">{t('legend_temp')}</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="w-3 h-1 border-b border-dashed border-[#22c55e]"></span>
                <span className="text-text-secondary">{t('legend_c')}</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="w-3 h-1 bg-[#137fec] rounded-full shadow-neon-blue"></span>
                <span className="text-text-secondary">{t('legend_v')}</span>
              </div>
           </div>
           
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
    </div>
  );
};

export default DynamicMonitor;
