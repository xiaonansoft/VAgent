import React, { useState, useEffect } from 'react';
import { fetchJsonRpc } from '../src/lib/mcp';
import { useProcessStream } from '../src/hooks/useProcessStream';
import { useLanguage } from '../src/contexts/LanguageContext';

interface Props {
  processContext?: any;
}

interface LanceStep {
  start_min: number;
  end_min: number;
  lance_height_mm: number;
}

interface LanceProfile {
  mode: string;
  steps: LanceStep[];
  endgame_action: string;
}

const LanceControl: React.FC<Props> = ({ processContext }) => {
  const { t } = useLanguage();
  const { data } = useProcessStream();
  const [recommendation, setRecommendation] = useState<LanceProfile | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    async function getRecommendation() {
      if (!processContext) return;
      
      setLoading(true);
      try {
        const result = await fetchJsonRpc('tools/call', {
          name: 'recommend_lance_profile',
          arguments: {
            si_content_pct: processContext.si_content_pct
          }
        });
        if (result && result.content) {
          // MCP returns content as an object, need to parse if it's a string or use directly
          // Based on tools_server.py: result={"content": out.model_dump(mode="json")}
          // So result.content is the LanceProfile object
          setRecommendation(result.content);
        }
      } catch (err) {
        console.error('Failed to get lance recommendation:', err);
      } finally {
        setLoading(false);
      }
    }

    getRecommendation();
  }, [processContext?.si_content_pct]);

  const currentHeight = data?.lance_height?.value;
  const processTimeMin = data?.process_time;
  const steps = recommendation?.steps ?? [];
  const totalDuration = steps.length > 0 ? Math.max(...steps.map(step => step.end_min)) : 6;
  const fallbackPath = "M 0 40 C 20 40, 40 40, 60 90 L 220 90 C 240 90, 240 130, 260 130 L 300 130";
  const fallbackArea = "M 0 40 L 60 90 L 220 90 L 260 130 L 300 130 V 150 H 0 Z";
  const minClamp = 8;
  const maxClamp = 140;

  const heightToY = (heightMm: number) => {
    const y = 398 - 0.3 * heightMm;
    return Math.min(maxClamp, Math.max(minClamp, y));
  };

  const timeToX = (timeMin: number) => {
    if (!totalDuration || totalDuration <= 0) return 0;
    return Math.min(300, Math.max(0, (timeMin / totalDuration) * 300));
  };

  const buildPath = () => {
    if (steps.length === 0) return fallbackPath;
    const points: Array<{ x: number; y: number }> = [];
    steps.forEach((step, index) => {
      const startX = timeToX(step.start_min);
      const endX = timeToX(step.end_min);
      const y = heightToY(step.lance_height_mm);
      if (index === 0) {
        points.push({ x: startX, y });
      } else {
        const prev = points[points.length - 1];
        if (prev.x !== startX || prev.y !== y) {
          points.push({ x: startX, y });
        }
      }
      points.push({ x: endX, y });
    });
    return points.map((p, idx) => `${idx === 0 ? "M" : "L"} ${p.x} ${p.y}`).join(" ");
  };

  const buildArea = () => {
    if (steps.length === 0) return fallbackArea;
    const points: Array<{ x: number; y: number }> = [];
    steps.forEach((step, index) => {
      const startX = timeToX(step.start_min);
      const endX = timeToX(step.end_min);
      const y = heightToY(step.lance_height_mm);
      if (index === 0) {
        points.push({ x: startX, y });
      } else {
        const prev = points[points.length - 1];
        if (prev.x !== startX || prev.y !== y) {
          points.push({ x: startX, y });
        }
      }
      points.push({ x: endX, y });
    });
    const first = points[0];
    const last = points[points.length - 1];
    const path = points.map((p, idx) => `${idx === 0 ? "M" : "L"} ${p.x} ${p.y}`).join(" ");
    return `${path} L ${last.x} 150 L ${first.x} 150 Z`;
  };

  const recommendationPath = buildPath();
  const recommendationArea = buildArea();
  const pickHeightForRange = (rangeStart: number, rangeEnd: number) => {
    if (steps.length === 0) return null;
    let best: LanceStep | null = null;
    let bestOverlap = -1;
    steps.forEach((step) => {
      const overlap = Math.min(step.end_min, rangeEnd) - Math.max(step.start_min, rangeStart);
      if (overlap > bestOverlap) {
        best = step;
        bestOverlap = overlap;
      }
    });
    if (!best || bestOverlap <= 0) return null;
    return best.lance_height_mm;
  };
  const phaseHeights = {
    ignition: pickHeightForRange(0, 0.5),
    main: pickHeightForRange(0.5, 5.5),
    end: pickHeightForRange(5.5, totalDuration)
  };
  const trendBreakpoints = steps.slice(1).reduce<Array<{ x: number; fromY: number; toY: number; direction: 'up' | 'down' }>>((acc, step, index) => {
    const prev = steps[index];
    if (prev.lance_height_mm === step.lance_height_mm) {
      return acc;
    }
    acc.push({
      x: timeToX(step.start_min),
      fromY: heightToY(prev.lance_height_mm),
      toY: heightToY(step.lance_height_mm),
      direction: step.lance_height_mm > prev.lance_height_mm ? 'up' : 'down'
    });
    return acc;
  }, []);
  const currentHeightY = typeof currentHeight === "number" ? heightToY(currentHeight) : null;
  const targetHeight = steps.length > 0 ? steps[steps.length - 1].lance_height_mm : null;
  const targetHeightY = typeof targetHeight === "number" ? heightToY(targetHeight) : null;
  const targetLabel = typeof targetHeight === "number" ? `${Math.round(targetHeight)}mm` : "--";
  const remainingSeconds = (() => {
    if (!steps.length || typeof processTimeMin !== "number") return null;
    const nextStep = steps.find(step => processTimeMin < step.end_min);
    if (!nextStep) return 0;
    return Math.max(0, Math.round((nextStep.end_min - processTimeMin) * 60));
  })();
  const operationHint = typeof remainingSeconds === 'number' && remainingSeconds <= 30
    ? t('operator_hint_prepare')
    : t('operator_hint_stable');
  const heightDeviation = typeof currentHeight === 'number' && typeof targetHeight === 'number'
    ? currentHeight - targetHeight
    : null;
  const immediateAction = heightDeviation === null
    ? t('adjust_hold_lance')
    : heightDeviation > 40
      ? t('adjust_lower_lance')
      : heightDeviation < -40
        ? t('adjust_raise_lance')
        : t('adjust_hold_lance');
  const adviceToneClass = heightDeviation === null
    ? 'text-text-secondary border-surface-border/50 bg-surface-dark/50'
    : Math.abs(heightDeviation) > 60
      ? 'text-status-alarm border-status-alarm/40 bg-status-alarm/10'
      : Math.abs(heightDeviation) > 30
        ? 'text-status-warning border-status-warning/40 bg-status-warning/10'
        : 'text-status-safe border-status-safe/40 bg-status-safe/10';

  return (
    <div className="min-h-[280px] bg-surface-dark/40 border border-surface-border rounded-xl flex flex-col shadow-lg relative overflow-hidden group hover:border-primary/30 transition-all duration-500">
      <div className="px-4 py-3 border-b border-surface-border/50 flex items-center justify-between bg-surface-dark/60 backdrop-blur-md z-10 gap-2">
        <div className="flex items-center gap-2">
          <div className="size-6 bg-primary/20 rounded flex items-center justify-center border border-primary/30">
            <span className="material-symbols-outlined text-primary text-sm animate-pulse">settings_input_component</span>
          </div>
          <h3 className="text-xs font-bold text-white tracking-widest uppercase">{t('lance_recommendation_title')}</h3>
        </div>
        <div className="flex gap-2 items-center flex-wrap justify-end">
          <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-md border bg-primary/10 border-primary/30">
            <span className="text-[9px] text-primary uppercase tracking-wider font-bold">{t('recommended_mode')}</span>
            <span className="text-[10px] font-bold text-primary">{recommendation?.mode ?? '--'}</span>
          </div>
          <div className="flex items-center gap-1.5 px-2 py-1 rounded-md border bg-surface-dark/80 border-surface-border">
            <span className="text-[9px] text-text-secondary font-bold">{t('phase_ignition')}</span>
            <span className="text-[10px] font-mono text-white">{typeof phaseHeights.ignition === 'number' ? Math.round(phaseHeights.ignition) : '--'}mm</span>
            <span className="text-[9px] text-text-secondary font-bold">{t('phase_main_blow')}</span>
            <span className="text-[10px] font-mono text-white">{typeof phaseHeights.main === 'number' ? Math.round(phaseHeights.main) : '--'}mm</span>
            <span className="text-[9px] text-text-secondary font-bold">{t('phase_end_pressing')}</span>
            <span className="text-[10px] font-mono text-white">{typeof phaseHeights.end === 'number' ? Math.round(phaseHeights.end) : '--'}mm</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="size-2 rounded-full bg-primary shadow-neon-blue"></span>
            <span className="text-[9px] text-text-secondary uppercase tracking-wider font-bold">{t('optimal')}</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="size-2 rounded-full bg-white/20 border border-white/50"></span>
            <span className="text-[9px] text-text-secondary uppercase tracking-wider font-bold">{t('actual')}</span>
          </div>
        </div>
      </div>
      
      <div className="flex flex-1 min-h-0">
        <div className="flex-1 flex flex-col min-h-0">
          <div className="flex-1 relative p-4 pt-3 pl-2">
          <svg className="w-full h-full overflow-visible" preserveAspectRatio="none" viewBox="0 0 300 150">
            <defs>
              <linearGradient id="optGradient" x1="0%" x2="0%" y1="0%" y2="100%">
                <stop offset="0%" style={{ stopColor: '#137fec', stopOpacity: 0.15 }}></stop>
                <stop offset="100%" style={{ stopColor: '#137fec', stopOpacity: 0 }}></stop>
              </linearGradient>
              <filter id="lance-glow">
                <feGaussianBlur result="coloredBlur" stdDeviation="2"></feGaussianBlur>
                <feMerge>
                  <feMergeNode in="coloredBlur"></feMergeNode>
                  <feMergeNode in="SourceGraphic"></feMergeNode>
                </feMerge>
              </filter>
            </defs>
            
            {/* Grid lines */}
            <g className="chart-grid opacity-20">
              {[40, 90, 130].map(y => (
                <line key={y} stroke="#fff" strokeDasharray="2,2" x1="0" x2="300" y1={y} y2={y}></line>
              ))}
            </g>
            
            {/* Y-axis labels */}
            <g className="text-[8px] fill-text-secondary font-mono opacity-80">
              <text x="0" y="38">1200mm</text>
              <text x="0" y="88">1000mm</text>
              <text x="0" y="128">900mm</text>
            </g>
            
            {/* Phase backgrounds */}
            <g className="opacity-5">
              <rect fill="#137fec" height="150" width="60" x="0" y="0"></rect>
              <rect fill="#22c55e" height="150" width="160" x="60" y="0"></rect>
              <rect fill="#f59e0b" height="150" width="80" x="220" y="0"></rect>
            </g>
            
            {/* Phase labels */}
            <g className="text-[8px] font-bold fill-white/20 uppercase tracking-widest" transform="translate(0, 143)">
              <text textAnchor="start" x="5">{t('phase_ignition')}</text>
              <text textAnchor="middle" x="140">{t('phase_main_blow')}</text>
              <text fill="#f59e0b" fillOpacity="0.6" textAnchor="end" x="295">{t('phase_end_pressing')}</text>
            </g>
            
            {/* Main Path */}
            <path 
              className="drop-shadow-[0_0_8px_rgba(19,127,236,0.4)] transition-all duration-1000" 
              d={recommendationPath}
              fill="none" 
              filter="url(#lance-glow)" 
              stroke="#137fec" 
              strokeLinecap="round" 
              strokeWidth="2.5"
            ></path>
            
            <path d={recommendationArea} fill="url(#optGradient)"></path>
            {trendBreakpoints.map((point, index) => (
              <g key={`trend-${index}`}>
                <line
                  x1={point.x}
                  x2={point.x}
                  y1={Math.min(point.fromY, point.toY) - 6}
                  y2={Math.max(point.fromY, point.toY) + 6}
                  stroke="#60a5fa"
                  strokeWidth="1.2"
                  strokeDasharray="2,2"
                  opacity="0.9"
                ></line>
                <circle cx={point.x} cy={point.fromY} fill="#dbeafe" r="2.2"></circle>
                <circle cx={point.x} cy={point.toY} fill="#137fec" r="3"></circle>
                <text
                  x={point.x + 4}
                  y={(point.fromY + point.toY) / 2 + 2}
                  fill={point.direction === 'up' ? '#22c55e' : '#f59e0b'}
                  fontFamily="monospace"
                  fontSize="9"
                  fontWeight="700"
                >
                  {point.direction === 'up' ? '↑' : '↓'}
                </text>
              </g>
            ))}
            
            {/* Actual Path */}
            {currentHeightY !== null && (
              <>
                <line x1="0" x2="300" y1={currentHeightY} y2={currentHeightY} stroke="white" strokeWidth="1.5" strokeDasharray="4,2"></line>
                <circle className="animate-pulse" cx="220" cy={currentHeightY} fill="#fff" filter="url(#glow)" r="2.5"></circle>
              </>
            )}
            
            {/* Target marker */}
            {targetHeightY !== null && (
              <g transform={`translate(260, ${targetHeightY})`}>
                <circle className="animate-ping opacity-50" fill="#f59e0b" r="4"></circle>
                <circle fill="#f59e0b" r="2.5"></circle>
                <text fill="#f59e0b" fontFamily="monospace" fontSize="8" fontWeight="bold" x="5" y="-5">{targetLabel}</text>
              </g>
            )}
          </svg>
          </div>
        </div>
        
        {/* Data Sidebar */}
        <div className="w-44 bg-surface-dark/80 p-5 flex flex-col justify-between z-10 backdrop-blur-md border-l border-surface-border/50">
          <div className="space-y-5">
            <div className="group/item">
              <div className="text-[9px] text-text-secondary uppercase tracking-widest font-bold mb-1.5 flex justify-between">
                <span>{t('current')}</span>
                <span className="text-primary group-hover:animate-pulse">{t('active')}</span>
              </div>
              <div className="flex items-baseline gap-1.5">
                <span className="text-2xl font-bold font-mono text-white tracking-tight">{typeof currentHeight === "number" ? Math.round(currentHeight) : "--"}</span>
                <span className="text-[10px] text-text-secondary font-sans">mm</span>
              </div>
              <div className="w-full h-1 bg-surface-border rounded-full mt-2 overflow-hidden">
                <div className="h-full bg-gradient-to-r from-primary/40 to-primary w-[75%] shadow-[0_0_8px_rgba(19,127,236,0.4)]"></div>
              </div>
            </div>
            
            <div>
              <div className="text-[9px] text-text-secondary uppercase tracking-widest font-bold mb-1.5">{t('target')}</div>
              <div className="flex items-baseline gap-1.5">
                <span className="text-2xl font-bold font-mono text-status-warning tracking-tight">{typeof targetHeight === "number" ? Math.round(targetHeight) : "--"}</span>
                <span className="text-[10px] text-text-secondary font-sans">mm</span>
              </div>
            </div>
            <div className="pt-4 border-t border-surface-border/50">
              <div className="text-[9px] text-text-secondary uppercase tracking-widest font-bold mb-2">{t('operation_advice')}</div>
              <div className={`rounded border px-2 py-1 text-[10px] font-bold uppercase tracking-wide ${adviceToneClass}`}>
                {t('immediate_action')}: {immediateAction}
              </div>
              <div className="text-[10px] text-text-secondary mt-2">
                {t('height_deviation')}: <span className="text-white font-mono">{heightDeviation === null ? '--' : `${heightDeviation > 0 ? '+' : ''}${Math.round(heightDeviation)}mm`}</span>
              </div>
              <div className="text-[10px] text-text-secondary mt-1">
                {t('follow_up_action')}: <span className="text-white">{recommendation?.endgame_action || operationHint}</span>
              </div>
            </div>
          </div>
          
          <div className="mt-4 pt-4 border-t border-surface-border/50">
            <div className="text-[9px] text-text-secondary uppercase tracking-widest font-bold mb-2 flex items-center gap-2">
              <span className="material-symbols-outlined text-[12px]">schedule</span>
              {t('next_step')}
            </div>
            <div className="flex items-center gap-3">
              <div className="flex flex-col">
                <span className="text-3xl font-bold font-mono text-white tracking-tighter leading-none">
                  {typeof remainingSeconds === "number" ? remainingSeconds : "--"}
                  <span className="text-xs ml-1 text-text-secondary">s</span>
                </span>
              </div>
              <div className="relative size-6 flex items-center justify-center">
                <div className="absolute inset-0 bg-primary/20 rounded-full animate-ping"></div>
                <div className="absolute inset-0 border border-primary/30 rounded-full"></div>
                <span className="material-symbols-outlined text-primary text-sm">hourglass_bottom</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default LanceControl;
