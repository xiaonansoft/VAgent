import React, { useEffect, useState } from 'react';
import { fetchJsonRpc } from '../src/lib/mcp';
import { useLanguage } from '../src/contexts/LanguageContext';

interface Props {
  processContext: any;
  setProcessContext: (ctx: any) => void;
}

const StaticSetup: React.FC<Props> = ({ processContext, setProcessContext }) => {
  const { t } = useLanguage();
  const [l1Data, setL1Data] = useState<any>(null);
  const [isLoading, setIsLoading] = useState(false);

  useEffect(() => {
    let isMounted = true;
    async function fetchData() {
      setIsLoading(true);
      try {
        const iron_analysis = { 
          C: 4.2, 
          Si: processContext.si_content_pct, 
          V: 0.28, 
          Ti: 0.1, 
          P: 0.08, 
          S: 0.03 
        };
        const res = await fetchJsonRpc('tools/call', {
          name: 'calculate_initial_charge',
          arguments: {
            iron_weight_t: 80.0,
            iron_temp_c: processContext.iron_temp_c,
            iron_analysis: iron_analysis,
            is_one_can: processContext.is_one_can,
          },
        });
        if (isMounted) {
          setL1Data(res.content);
        }
      } catch (e) {
        console.error("L1 Data fetch error:", e);
      } finally {
        if (isMounted) {
          setIsLoading(false);
        }
      }
    }
    fetchData();
    return () => { isMounted = false; };
  }, [processContext.si_content_pct, processContext.iron_temp_c, processContext.is_one_can]);

  const chemicals = React.useMemo(() => [
    { label: 'V', value: '0.28%', isPrimary: true },
    { label: 'Si', value: `${processContext.si_content_pct}%` },
    { label: 'Ti', value: '0.10%' },
    { label: 'C', value: '4.2%' },
    { label: 'Mn', value: '0.2%' },
    { label: 'P', value: '0.08%' },
    { label: 'S', value: '0.03%', colSpan: 2 },
  ], [processContext.si_content_pct]);

  return (
    <div className="flex flex-col gap-4 h-full">
      <div className="flex items-center gap-2 mb-1 pl-1">
        <span className="material-symbols-outlined text-primary text-xl">tune</span>
        <h1 className="text-white text-base font-bold tracking-wide">{t('static_setup_title')}</h1>
      </div>

      {/* Hot Metal Panel */}
      <div className="glass-panel rounded-xl p-5 flex flex-col gap-4 shadow-lg hover:border-primary/30 transition-all duration-300">
        <div className="flex justify-between items-center border-b border-surface-border/50 pb-3">
          <h3 className="text-white font-bold text-sm flex items-center gap-2">
            <span className="w-1 h-4 bg-primary rounded-full"></span>
            {t('hot_metal')}
          </h3>
          <span className="text-[10px] font-mono text-primary bg-primary/10 px-2 py-0.5 rounded border border-primary/20">{t('batch_no')}</span>
        </div>
        <div className="grid grid-cols-2 gap-4">
          <div className="flex flex-col p-3 bg-surface-dark/50 rounded-lg border border-surface-border/30 hover:border-primary/20 transition-colors">
            <span className="text-text-secondary text-[10px] uppercase tracking-wider mb-1">{t('weight')}</span>
            <div className="text-2xl font-bold font-mono text-white tracking-tight">80.0<span className="text-sm text-text-secondary ml-1 font-sans">t</span></div>
          </div>
          <div className="flex flex-col p-3 bg-surface-dark/50 rounded-lg border border-surface-border/30 hover:border-primary/20 transition-colors">
            <span className="text-text-secondary text-[10px] uppercase tracking-wider mb-1">{t('temp')}</span>
            <div className="text-2xl font-bold font-mono text-white tracking-tight">{processContext.iron_temp_c}<span className="text-sm text-text-secondary ml-1 font-sans">°C</span></div>
          </div>
        </div>
        <div className="bg-[#0b1116] rounded-lg p-4 grid grid-cols-4 gap-y-4 gap-x-2 border border-surface-border/50 shadow-inner">
          {chemicals.map((item, index) => (
            <div key={index} className={`flex flex-col items-center ${item.colSpan ? 'col-span-2' : ''}`}>
              <span className="text-[9px] text-text-secondary font-bold mb-0.5">{item.label}</span>
              <span className={`text-xs font-mono transition-colors ${item.isPrimary ? 'text-primary font-bold' : 'text-white'}`}>{item.value}</span>
            </div>
          ))}
        </div>
        <div className="flex items-center justify-between pt-1 px-1">
          <span className="text-xs font-medium text-white">{t('one_ladle')}</span>
          <button 
            onClick={() => setProcessContext((prev: any) => ({ ...prev, is_one_can: !prev.is_one_can }))}
            className={`flex items-center gap-2 px-3 py-1 rounded-full border transition-all duration-300 cursor-pointer ${
              processContext.is_one_can 
                ? 'bg-status-safe/10 border-status-safe text-status-safe shadow-[0_0_10px_rgba(34,197,94,0.1)]' 
                : 'bg-surface-dark/80 border-surface-border text-text-secondary hover:border-gray-500'
            }`}
          >
            <span className={`size-2 rounded-full transition-all ${processContext.is_one_can ? 'bg-status-safe shadow-[0_0_8px_theme("colors.status-safe")]' : 'bg-text-secondary'}`}></span>
            <span className="text-[10px] font-bold uppercase tracking-wider">{processContext.is_one_can ? t('active_status') : t('inactive_status')}</span>
        </button>
      </div>
    </div>

    {/* Recipe Panel */}
    <div className="glass-panel rounded-xl p-5 flex flex-col gap-5 shadow-lg flex-1 hover:border-status-warning/30 transition-all duration-300">
      <div className="flex justify-between items-center border-b border-surface-border/50 pb-3">
        <h3 className="text-white font-bold text-sm flex items-center gap-2">
          <span className="w-1 h-4 bg-status-warning rounded-full animate-pulse"></span>
          {t('recipe_recommendation')}
        </h3>
        <button className="text-primary hover:text-white text-[10px] font-bold uppercase transition-all tracking-wider border border-surface-border px-2 py-1 rounded hover:bg-primary/10 hover:border-primary/50 cursor-pointer">{t('edit')}</button>
      </div>
        <div className="space-y-5 flex-1">
          {isLoading ? (
            <div className="flex flex-col gap-4 animate-pulse">
              {[1, 2].map(i => (
                <div key={i} className="space-y-2">
                  <div className="h-3 w-20 bg-surface-border rounded"></div>
                  <div className="h-1.5 w-full bg-surface-border rounded-full"></div>
                </div>
              ))}
            </div>
          ) : l1Data ? (
            Object.entries(l1Data.recipe).map(([name, weight]: any, i) => (
              <div key={i} className="group">
                <div className="flex justify-between text-xs mb-1.5">
                  <span className="text-white font-medium group-hover:text-primary transition-colors">{name}</span>
                  <span className="font-mono text-primary font-bold">{weight}t</span>
                </div>
                <div className="h-1.5 w-full bg-surface-border rounded-full overflow-hidden">
                  <div 
                    className="h-full bg-primary rounded-full shadow-neon-blue transition-all duration-1000 ease-out" 
                    style={{ width: `${Math.min(100, (weight / 5) * 100)}%` }}
                  ></div>
                </div>
              </div>
            ))
          ) : (
            <div className="text-center text-text-secondary text-xs italic py-4">No data available</div>
          )}
          
          <div className="pt-2">
          <div className="flex justify-between text-xs mb-2">
            <span className="text-text-secondary uppercase font-bold text-[10px] tracking-wider">{t('cooling_intensity')}</span>
            <span className="text-status-warning font-mono font-bold text-xs shadow-neon-amber">{t('high')}</span>
          </div>
          <div className="flex gap-1 h-2">
              {[1, 2, 3, 4, 5, 6].map((i) => (
                <div key={i} className="flex-1 bg-primary rounded-sm shadow-[0_0_5px_rgba(19,127,236,0.3)]"></div>
              ))}
              <div className="flex-1 bg-primary/30 rounded-sm"></div>
              <div className="flex-1 bg-surface-border rounded-sm"></div>
            </div>
          </div>
        </div>
        
        {/* Progress Bar */}
        <div className="mt-auto border border-primary/30 bg-primary/5 rounded-lg p-4 relative overflow-hidden group hover:bg-primary/10 transition-colors">
          <div className="absolute inset-0 bg-gradient-to-r from-transparent via-primary/10 to-transparent -translate-x-full group-hover:translate-x-full transition-transform duration-1500"></div>
          <div className="flex justify-between items-center mb-2">
          <div className="flex items-center gap-2">
            <span className="material-symbols-outlined text-primary text-base animate-spin">sync</span>
            <span className="text-xs font-bold text-white uppercase tracking-wide">{t('adding_coolant')}</span>
          </div>
          <span className="text-xs font-mono text-white">0.8t <span className="text-text-secondary mx-0.5">/</span> {l1Data ? (Object.values(l1Data.recipe) as number[]).reduce((a: number, b: number) => a + b, 0) : 3.5}t</span>
        </div>
          <div className="h-2 w-full bg-surface-border/50 rounded-full overflow-hidden relative">
            <div className="absolute inset-y-0 left-0 bg-primary w-[20%] rounded-full shadow-neon-blue animate-load-bar"></div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default StaticSetup;