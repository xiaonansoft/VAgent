import React, { useState, useEffect, useMemo } from 'react';
import { debounce } from 'lodash';
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Line, Legend, ReferenceLine } from 'recharts';

interface SimulationPoint {
  time_s: number;
  temp_c: number;
  C_pct: number;
  V_pct: number;
  uncertainty_sigma?: number;
  // Computed for chart
  temp_lower?: number;
  temp_upper?: number;
}

const WhatIfSandbox = () => {
  // --- Process Inputs ---
  // Iron Conditions
  const [ironTemp, setIronTemp] = useState(1350);
  const [ironWeight, setIronWeight] = useState(100);
  const [siContent, setSiContent] = useState(0.20);
  const [vContent, setVContent] = useState(0.28);
  
  // Additions (Recipe)
  const [scaleWeight, setScaleWeight] = useState(0.0);
  const [limeWeight, setLimeWeight] = useState(2.0);
  
  // Process Parameters
  const [oxygenFlow, setOxygenFlow] = useState(22000);
  const [duration, setDuration] = useState(360);

  // --- Simulation State ---
  const [sandboxData, setSandboxData] = useState<SimulationPoint[]>([]); 
  const [results, setResults] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Fetch Simulation Function
  const fetchSimulation = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch('/api/simulation/run', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
            initial_temp_c: ironTemp,
            initial_analysis: {
                C: 4.2, // Default C
                Si: siContent, 
                V: vContent, 
                Ti: 0.1, 
                P: 0.08, 
                S: 0.03
            },
            recipe: {
                iron_weight: ironWeight, 
                scale_weight: scaleWeight,
                lime_weight: limeWeight
            }, 
            oxygen_flow_rate_m3h: oxygenFlow,
            duration_s: duration,
            off_gas_correction: false
        })
      });
      
      if (!response.ok) {
          throw new Error("Simulation failed");
      }

      const data = await response.json();
      
      const processedPoints = data.points.map((p: any) => {
          const sigma = p.uncertainty_sigma || 0;
          const temp_sigma = sigma * 100; // Amplify for visualization
          
          return {
            ...p,
            temp_lower: p.temp_c - 1.96 * temp_sigma,
            temp_upper: p.temp_c + 1.96 * temp_sigma,
          };
      });
      
      setSandboxData(processedPoints);
      setResults(data);
    } catch (e: any) {
      console.error(e);
      setError(e.message || "Simulation failed");
    } finally {
        setLoading(false);
    }
  };

  // Debounce Simulation Trigger
  const debouncedFetch = useMemo(() => debounce(fetchSimulation, 800), [
      ironTemp, ironWeight, siContent, vContent, 
      scaleWeight, limeWeight, 
      oxygenFlow, duration
  ]);

  useEffect(() => {
    debouncedFetch();
    return () => debouncedFetch.cancel();
  }, [
      ironTemp, ironWeight, siContent, vContent, 
      scaleWeight, limeWeight, 
      oxygenFlow, duration
  ]);

  // --- Helper Components ---
  const InputField = ({ label, value, onChange, min, max, step, unit }: any) => (
    <div className="flex flex-col gap-1">
      <div className="flex justify-between text-xs text-gray-400">
        <span>{label}</span>
        <span className="font-mono text-primary">{value} {unit}</span>
      </div>
      <input 
        type="range" 
        min={min} max={max} step={step} 
        value={value} 
        onChange={e => onChange(parseFloat(e.target.value))}
        className="w-full h-1.5 bg-gray-700 rounded-lg appearance-none cursor-pointer accent-primary hover:accent-blue-400 transition-all"
      />
      <div className="flex justify-between text-[10px] text-gray-600 font-mono">
        <span>{min}</span>
        <span>{max}</span>
      </div>
    </div>
  );

  const KPICard = ({ title, value, unit, subValue, status = "normal" }: any) => (
      <div className={`p-3 rounded-lg border ${
          status === 'warning' ? 'bg-status-warning/10 border-status-warning/30' : 
          status === 'alarm' ? 'bg-status-alarm/10 border-status-alarm/30' : 
          'bg-surface-dark border-surface-border'
      }`}>
          <div className="text-[10px] uppercase tracking-wider text-text-secondary mb-1">{title}</div>
          <div className={`text-2xl font-mono font-bold ${
              status === 'warning' ? 'text-status-warning' : 
              status === 'alarm' ? 'text-status-alarm' : 
              'text-white'
          }`}>
              {value} <span className="text-sm font-normal text-gray-500">{unit}</span>
          </div>
          {subValue && <div className="text-xs text-gray-400 mt-1">{subValue}</div>}
      </div>
  );

  return (
    <div className="flex flex-col h-full gap-6 p-2">
      <div className="flex items-center justify-between">
          <h2 className="text-xl font-bold flex items-center gap-2 text-white">
            <span className="material-symbols-outlined text-primary">science</span> 
            炼钢工艺仿真计算器
          </h2>
          <div className="flex gap-2">
            {loading && <span className="flex items-center gap-2 text-xs text-primary animate-pulse"><span className="w-2 h-2 rounded-full bg-primary"></span> 计算中...</span>}
            <button 
                onClick={fetchSimulation}
                className="px-3 py-1 bg-primary hover:bg-blue-600 text-white text-xs font-bold rounded flex items-center gap-1 transition-colors"
            >
                <span className="material-symbols-outlined text-sm">refresh</span>
                重新计算
            </button>
          </div>
      </div>

      <div className="flex-1 grid grid-cols-1 lg:grid-cols-12 gap-6 min-h-0">
        {/* --- Left Panel: Input Configuration --- */}
        <div className="lg:col-span-4 flex flex-col gap-6 overflow-y-auto pr-2 custom-scrollbar">
            
            {/* Group 1: Iron Conditions */}
            <div className="bg-surface-dark/50 border border-surface-border rounded-xl p-4">
                <h3 className="text-sm font-bold text-white mb-4 flex items-center gap-2">
                    <span className="w-1 h-4 bg-status-safe rounded-full"></span>
                    铁水条件
                </h3>
                <div className="space-y-5">
                    <InputField label="铁水重量" value={ironWeight} onChange={setIronWeight} min={50} max={150} step={1} unit="t" />
                    <InputField label="入炉温度" value={ironTemp} onChange={setIronTemp} min={1200} max={1500} step={5} unit="°C" />
                    <InputField label="[Si] 硅含量" value={siContent} onChange={setSiContent} min={0.05} max={1.0} step={0.01} unit="%" />
                    <InputField label="[V] 钒含量" value={vContent} onChange={setVContent} min={0.1} max={0.5} step={0.01} unit="%" />
                </div>
            </div>

            {/* Group 2: Additions */}
            <div className="bg-surface-dark/50 border border-surface-border rounded-xl p-4">
                <h3 className="text-sm font-bold text-white mb-4 flex items-center gap-2">
                    <span className="w-1 h-4 bg-status-warning rounded-full"></span>
                    辅料加入 (配方)
                </h3>
                <div className="space-y-5">
                    <InputField label="氧化铁皮" value={scaleWeight} onChange={setScaleWeight} min={0} max={10} step={0.1} unit="t" />
                    <InputField label="石灰" value={limeWeight} onChange={setLimeWeight} min={0} max={5} step={0.1} unit="t" />
                </div>
            </div>

            {/* Group 3: Operation */}
            <div className="bg-surface-dark/50 border border-surface-border rounded-xl p-4">
                <h3 className="text-sm font-bold text-white mb-4 flex items-center gap-2">
                    <span className="w-1 h-4 bg-status-alarm rounded-full"></span>
                    操作参数
                </h3>
                <div className="space-y-5">
                    <InputField label="供氧流量" value={oxygenFlow} onChange={setOxygenFlow} min={15000} max={35000} step={500} unit="Nm³/h" />
                    <InputField label="吹炼时长" value={duration} onChange={setDuration} min={180} max={600} step={10} unit="s" />
                </div>
            </div>
        </div>

        {/* --- Right Panel: Results --- */}
        <div className="lg:col-span-8 flex flex-col gap-4 min-h-0">
            {/* KPI Cards */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                <KPICard 
                    title="终点温度" 
                    value={results?.final_temp_c ?? '--'} 
                    unit="°C" 
                    status={results?.final_temp_c > 1400 ? 'alarm' : results?.final_temp_c < 1340 ? 'warning' : 'normal'}
                />
                <KPICard 
                    title="终点 [C]" 
                    value={results?.final_analysis?.C?.toFixed(2) ?? '--'} 
                    unit="%" 
                />
                <KPICard 
                    title="终点 [V]" 
                    value={results?.final_analysis?.V?.toFixed(3) ?? '--'} 
                    unit="%" 
                />
                <KPICard 
                    title="Tc 转化点" 
                    value={results?.tc_crossover_s ?? '未到达'} 
                    unit={results?.tc_crossover_s ? "s" : ""} 
                    subValue={results?.tc_crossover_s ? `约在进程 ${Math.round((results.tc_crossover_s / duration) * 100)}% 处` : '未检测到转化点'}
                />
            </div>

            {/* Main Chart */}
            <div className="flex-1 bg-surface-dark border border-surface-border rounded-xl p-4 min-h-[300px] relative">
                <h3 className="text-xs font-bold text-gray-400 absolute top-4 left-4 z-10">动力学仿真趋势图</h3>
                <ResponsiveContainer width="100%" height="100%">
                    <AreaChart data={sandboxData} margin={{ top: 25, right: 20, left: -10, bottom: 0 }}>
                        <defs>
                            <linearGradient id="colorTemp" x1="0" y1="0" x2="0" y2="1">
                                <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.3}/>
                                <stop offset="95%" stopColor="#3b82f6" stopOpacity={0}/>
                            </linearGradient>
                        </defs>
                        <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#334155" opacity={0.5} />
                        <XAxis 
                            dataKey="time_s" 
                            stroke="#94a3b8" 
                            fontSize={10} 
                            tickFormatter={v => `${(v/60).toFixed(1)}m`}
                        />
                        <YAxis 
                            yAxisId="temp" 
                            domain={['auto', 'auto']} 
                            stroke="#3b82f6" 
                            fontSize={10}
                            unit="°C"
                        />
                        <YAxis 
                            yAxisId="chem" 
                            orientation="right" 
                            domain={[0, 4.5]} 
                            stroke="#22c55e" 
                            fontSize={10}
                            unit="%"
                        />
                        <Tooltip 
                            contentStyle={{ backgroundColor: '#1e293b', borderColor: '#334155', color: '#f8fafc' }}
                            labelFormatter={v => `${(v/60).toFixed(1)} min`}
                        />
                        <Legend wrapperStyle={{ fontSize: '10px' }} />
                        
                        {/* Reference Lines */}
                        <ReferenceLine y={1380} yAxisId="temp" stroke="#ef4444" strokeDasharray="3 3" label={{ value: 'Tc Limit', fill: '#ef4444', fontSize: 10, position: 'insideRight' }} />

                        {/* Temp with Confidence Band */}
                        <Area 
                            yAxisId="temp"
                            type="monotone" 
                            dataKey="temp_c" 
                            stroke="#3b82f6" 
                            fillOpacity={1} 
                            fill="url(#colorTemp)" 
                            name="熔池温度"
                            strokeWidth={2}
                        />
                        
                        {/* Chemistry Lines */}
                        <Line yAxisId="chem" type="monotone" dataKey="C_pct" stroke="#22c55e" strokeWidth={2} dot={false} name="碳含量 %" />
                        <Line yAxisId="chem" type="monotone" dataKey="V_pct" stroke="#a855f7" strokeWidth={2} dot={false} name="钒含量 %" />
                        <Line yAxisId="chem" type="monotone" dataKey="Si_pct" stroke="#f59e0b" strokeWidth={1} strokeDasharray="3 3" dot={false} name="硅含量 %" />
                    </AreaChart>
                </ResponsiveContainer>
            </div>
            
            {/* Advice / Alerts */}
            {results?.proactive_advice && (
                <div className="bg-blue-500/10 border border-blue-500/30 p-3 rounded-lg flex items-start gap-3">
                    <span className="material-symbols-outlined text-blue-400">info</span>
                    <div>
                        <div className="text-sm font-bold text-blue-400 mb-1">工艺建议</div>
                        <div className="text-xs text-gray-300">{results.proactive_advice}</div>
                    </div>
                </div>
            )}
        </div>
      </div>
    </div>
  );
};

export default WhatIfSandbox;
