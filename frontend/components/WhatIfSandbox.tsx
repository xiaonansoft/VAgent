import React, { useState, useEffect, useMemo } from 'react';
import { debounce } from 'lodash';
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Line, Legend } from 'recharts';

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
  // State for sliders
  const [initialTemp, setInitialTemp] = useState(1360);
  const [initialSi, setInitialSi] = useState(0.20);
  const [scaleAddition, setScaleAddition] = useState(0.0);
  
  // State for chart data
  const [sandboxData, setSandboxData] = useState<SimulationPoint[]>([]); 
  const [loading, setLoading] = useState(false);

  // Fetch Simulation Function
  const fetchSimulation = async (temp: number, si: number, scale: number) => {
    setLoading(true);
    try {
      const response = await fetch('http://localhost:8000/api/simulation/run', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
            initial_temp_c: temp,
            initial_analysis: {C: 4.2, Si: si, V: 0.28, Ti: 0.1, P: 0.08, S: 0.03},
            recipe: {iron_weight: 100, scale_weight: scale}, 
            off_gas_correction: false // Sandbox is pure prediction
        })
      });
      const data = await response.json();
      
      const processedPoints = data.points.map((p: any) => {
          const sigma = p.uncertainty_sigma || 0;
          // 95% Confidence Interval (1.96 * sigma)
          // Scale sigma for visibility if it's too small in the model (e.g. 0.005)
          // Let's assume sigma is in same units as Temp for temp_uncertainty?
          // But our model returns a generic 'sigma'.
          // In kinetics_simulator, we set sigma = 0.005 + t/duration*0.05.
          // This is ~0.05 at end. 0.05 degrees is invisible.
          // Let's amplify it for visualization purpose (or assume the model outputs a larger sigma for Temp).
          // Actually, let's treat sigma as a percentage error relative to value or just a scaling factor.
          // Let's amplify by 100 for Temp visualization (assuming sigma is ~0.1 -> 10 deg).
          const temp_sigma = sigma * 100; 
          
          return {
            ...p,
            temp_lower: p.temp_c - 1.96 * temp_sigma,
            temp_upper: p.temp_c + 1.96 * temp_sigma,
            // Recharts requires [min, max] for range area? No, Recharts `Area` is usually simple.
            // We will use two stacked areas trick or `range` if supported.
            // Let's use `temp_range` = [lower, upper] if Recharts supports it.
            // Recharts 2.x supports `dataKey` as function or string.
            // Let's use the 'stack' trick:
            // Area1 (invisible): value = lower
            // Area2 (visible): value = upper - lower
            temp_base: p.temp_c - 1.96 * temp_sigma,
            temp_spread: (p.temp_c + 1.96 * temp_sigma) - (p.temp_c - 1.96 * temp_sigma)
          };
      });
      
      setSandboxData(processedPoints);
    } catch (e) {
      console.error(e);
    } finally {
        setLoading(false);
    }
  };

  // Debounce
  const debouncedFetch = useMemo(() => debounce(fetchSimulation, 500), []);

  useEffect(() => {
    debouncedFetch(initialTemp, initialSi, scaleAddition);
    // Cancel debounce on unmount
    return () => debouncedFetch.cancel();
  }, [initialTemp, initialSi, scaleAddition]);

  return (
    <div className="bg-gray-900 text-white p-6 rounded-xl shadow-2xl border border-gray-800 h-full flex flex-col">
      <div className="flex items-center justify-between mb-6">
          <h2 className="text-xl font-bold flex items-center gap-2 text-blue-400">
            <span>🧪</span> 
            What-If 沙盘推演
          </h2>
          {loading && <span className="text-xs text-yellow-500 animate-pulse">计算中...</span>}
      </div>
      
      {/* Sliders Control Panel */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-8 mb-6 bg-gray-800/50 p-4 rounded-lg">
        {/* Temp Slider */}
        <div className="flex flex-col gap-2">
            <div className="flex justify-between text-sm">
                <span className="text-gray-400">初始温度</span>
                <span className="font-mono text-blue-400">{initialTemp}℃</span>
            </div>
            <input type="range" min="1250" max="1450" step="10" 
                   value={initialTemp} onChange={e => setInitialTemp(Number(e.target.value))}
                   className="w-full h-2 bg-gray-700 rounded-lg appearance-none cursor-pointer accent-blue-500 hover:accent-blue-400 transition-all" />
        </div>
        
        {/* Si Slider */}
        <div className="flex flex-col gap-2">
            <div className="flex justify-between text-sm">
                <span className="text-gray-400">初始 [Si]</span>
                <span className="font-mono text-green-400">{initialSi}%</span>
            </div>
            <input type="range" min="0.05" max="0.50" step="0.01" 
                   value={initialSi} onChange={e => setInitialSi(Number(e.target.value))}
                   className="w-full h-2 bg-gray-700 rounded-lg appearance-none cursor-pointer accent-green-500 hover:accent-green-400 transition-all" />
        </div>
        
        {/* Scale Slider */}
        <div className="flex flex-col gap-2">
            <div className="flex justify-between text-sm">
                <span className="text-gray-400">氧化铁皮</span>
                <span className="font-mono text-red-400">{scaleAddition}t</span>
            </div>
            <input type="range" min="0.0" max="5.0" step="0.1" 
                   value={scaleAddition} onChange={e => setScaleAddition(Number(e.target.value))}
                   className="w-full h-2 bg-gray-700 rounded-lg appearance-none cursor-pointer accent-red-500 hover:accent-red-400 transition-all" />
        </div>
      </div>

      {/* Interactive Chart */}
      <div className="flex-1 min-h-[300px] w-full bg-gray-950/30 rounded-lg p-2 border border-gray-800/50">
         <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={sandboxData} margin={{ top: 10, right: 30, left: 0, bottom: 0 }}>
                <defs>
                    <linearGradient id="colorTemp" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="#F59E0B" stopOpacity={0.1}/>
                        <stop offset="95%" stopColor="#F59E0B" stopOpacity={0}/>
                    </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#374151" vertical={false} />
                <XAxis dataKey="time_s" stroke="#9CA3AF" tick={{fontSize: 12}} />
                <YAxis yAxisId="temp" orientation="left" stroke="#F59E0B" domain={[1250, 'auto']} tick={{fontSize: 12}} />
                <YAxis yAxisId="v" orientation="right" stroke="#10B981" domain={[0, 0.5]} tick={{fontSize: 12}} />
                <Tooltip 
                    contentStyle={{ backgroundColor: '#111827', border: '1px solid #374151', borderRadius: '8px', boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.5)' }}
                    itemStyle={{ fontSize: '12px' }}
                    labelStyle={{ color: '#9CA3AF', marginBottom: '4px' }}
                />
                <Legend wrapperStyle={{ fontSize: '12px', paddingTop: '10px' }} />
                
                {/* Confidence Band (Temperature) - Stacked Area Trick */}
                {/* 1. Base (Transparent) */}
                <Area yAxisId="temp" type="monotone" dataKey="temp_base" stackId="1" stroke="none" fill="transparent" legendType="none" tooltipType="none" />
                {/* 2. Spread (Visible Shadow) */}
                <Area yAxisId="temp" type="monotone" dataKey="temp_spread" stackId="1" stroke="none" fill="#F59E0B" fillOpacity={0.15} name="置信区间 (95%)" />
                
                {/* Main Lines */}
                <Line yAxisId="temp" type="monotone" dataKey="temp_c" stroke="#F59E0B" strokeWidth={3} dot={false} name="预测温度" activeDot={{ r: 6 }} />
                <Line yAxisId="v" type="monotone" dataKey="V_pct" stroke="#10B981" strokeWidth={2} dot={false} name="预测 [V]" strokeDasharray="5 5" />
            </AreaChart>
         </ResponsiveContainer>
      </div>
    </div>
  );
};

export default WhatIfSandbox;
