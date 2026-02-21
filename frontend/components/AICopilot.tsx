import React, { useState, useRef, useEffect, useCallback } from 'react';
import { chatWithAgent } from '../src/lib/mcp';
import { useLanguage } from '../src/contexts/LanguageContext';

interface Props {
  processContext: any;
}

const AICopilot: React.FC<Props> = React.memo(({ processContext }) => {
  const { t } = useLanguage();
  const [chatInput, setChatInput] = useState('');
  const [messages, setMessages] = useState<any[]>([
    {
      id: '1',
      type: 'recommendation',
      content: t('ai_welcome'),
      timestamp: new Date().toLocaleTimeString(),
    }
  ]);
  const [isLoading, setIsLoading] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (scrollRef.current) {
      const scrollOptions: ScrollToOptions = {
        top: scrollRef.current.scrollHeight,
        behavior: 'smooth'
      };
      scrollRef.current.scrollTo(scrollOptions);
    }
  }, [messages]);

  const handleSend = useCallback(async () => {
    if (!chatInput.trim() || isLoading) return;
    
    const currentInput = chatInput;
    setChatInput('');
    setIsLoading(true);

    const userMsg = {
      id: Date.now().toString(),
      type: 'user',
      content: currentInput,
      timestamp: new Date().toLocaleTimeString(),
    };
    
    setMessages(prev => [...prev, userMsg]);

    try {
      const res = await chatWithAgent(currentInput, processContext);
      const aiMsg = {
        id: (Date.now() + 1).toString(),
        type: 'recommendation',
        content: res.reply,
        timestamp: new Date().toLocaleTimeString(),
        traceId: res.trace_id
      };
      setMessages(prev => [...prev, aiMsg]);
    } catch (e) {
      console.error("Chat error:", e);
      setMessages(prev => [...prev, {
        id: (Date.now() + 1).toString(),
        type: 'warning',
        content: t('ai_connect_fail'),
        timestamp: new Date().toLocaleTimeString(),
      }]);
    } finally {
      setIsLoading(false);
    }
  }, [chatInput, isLoading, processContext]);

  return (
    <div className="flex flex-col gap-4 h-full">
      <div className="flex items-center gap-2 mb-1 pl-1">
        <span className="material-symbols-outlined text-purple-400 text-xl animate-bounce-slow">smart_toy</span>
        <h1 className="text-white text-base font-bold tracking-wide">{t('ai_copilot_title')}</h1>
      </div>

      <div className="flex-1 glass-panel rounded-xl overflow-hidden flex flex-col shadow-lg border border-purple-500/20 hover:border-purple-500/40 transition-colors duration-500">
        <div className="p-4 border-b border-surface-border bg-surface-dark flex items-center gap-3">
          <div className="relative">
            <div className="size-9 rounded-full bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center shadow-[0_0_10px_theme('colors.purple.500')]">
              <span className="material-symbols-outlined text-white text-lg">auto_awesome</span>
            </div>
            <div className="absolute -bottom-0.5 -right-0.5 size-2.5 bg-status-safe border-2 border-surface-dark rounded-full animate-pulse"></div>
          </div>
          <div>
            <h3 className="text-sm font-bold text-white">{t('strategy_feed')}</h3>
            <p className="text-[10px] text-text-secondary flex items-center gap-1">
              <span className="material-symbols-outlined text-[10px] animate-pulse">bolt</span>
              Kinetic-V7.2
            </p>
          </div>
        </div>
        
        {/* Feed Content */}
        <div ref={scrollRef} className="flex-1 overflow-y-auto p-4 space-y-4 bg-[#0b1116]/80 scroll-smooth custom-scrollbar">
          {messages.map((msg) => (
            <React.Fragment key={msg.id}>
              <div className="flex items-center justify-center gap-2 my-2 opacity-30">
                <div className="h-px bg-surface-border w-8"></div>
                <span className="text-[9px] text-text-secondary font-mono">{msg.timestamp}</span>
                <div className="h-px bg-surface-border w-8"></div>
              </div>
              
              <div className={`flex gap-3 animate-fade-in-up ${msg.type === 'user' ? 'flex-row-reverse' : ''}`}>
                <div className="flex-shrink-0 mt-1">
                  <div className={`size-6 rounded flex items-center justify-center border transition-all duration-300 ${
                    msg.type === 'user' ? 'bg-indigo-500/20 text-indigo-400 border-indigo-500/30' :
                    msg.type === 'warning' ? 'bg-status-warning/20 text-status-warning border-status-warning/30' :
                    'bg-primary/20 text-primary border-primary/30 shadow-neon-blue'
                  }`}>
                    <span className="material-symbols-outlined text-sm">
                      {msg.type === 'user' ? 'person' : msg.type === 'warning' ? 'warning' : 'auto_awesome'}
                    </span>
                  </div>
                </div>
                <div className={`rounded-lg rounded-tl-none p-3 text-sm max-w-[90%] border transition-all duration-300 ${
                  msg.type === 'user' ? 'bg-indigo-500/5 border-indigo-500/20' :
                  msg.type === 'warning' ? 'bg-status-warning/5 border border-status-warning/20' :
                  'bg-primary/5 border border-primary/20 hover:bg-primary/10'
                }`}>
                  <p className={`font-bold text-[10px] mb-1 uppercase tracking-wider ${
                    msg.type === 'user' ? 'text-indigo-400' :
                    msg.type === 'warning' ? 'text-status-warning' :
                    'text-primary'
                  }`}>
                    {msg.type === 'user' ? t('role_user') : msg.type === 'warning' ? t('role_alert') : t('role_recommendation')}
                  </p>
                  <p className="text-gray-300 text-xs leading-relaxed whitespace-pre-wrap">{msg.content}</p>
                  {msg.traceId && (
                    <div className="mt-2 pt-2 border-t border-white/10 flex items-center gap-1 text-[9px] text-text-secondary font-mono opacity-50">
                      <span className="material-symbols-outlined text-[10px]">fingerprint</span>
                      <span>Trace ID: {msg.traceId}</span>
                    </div>
                  )}
                </div>
              </div>
            </React.Fragment>
          ))}
          {isLoading && (
            <div className="flex gap-3 animate-pulse">
              <div className="size-6 rounded bg-primary/10 border border-primary/20"></div>
              <div className="flex-1 space-y-2">
                <div className="h-4 w-1/4 bg-primary/10 rounded"></div>
                <div className="h-10 w-full bg-primary/5 rounded-lg border border-primary/10"></div>
              </div>
            </div>
          )}
        </div>

        <div className="p-3 border-t border-surface-border bg-surface-dark/90 backdrop-blur">
          <div className="flex gap-2">
            <input 
              className="w-full bg-[#0b1116] border border-surface-border rounded text-xs text-white px-3 py-2.5 focus:border-primary focus:ring-1 focus:ring-primary outline-none placeholder-gray-600 transition-all" 
              placeholder={t('chat_placeholder')}
              type="text"
              aria-label="AI Chat Input"
              value={chatInput}
              onChange={(e) => setChatInput(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleSend()}
            />
            <button 
              onClick={handleSend} 
              disabled={isLoading}
              aria-label="Send Message"
              className="bg-primary hover:bg-blue-600 text-white p-2 rounded flex items-center justify-center transition-all shadow-neon-blue cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed active:scale-95"
            >
              <span className="material-symbols-outlined text-sm">{isLoading ? 'sync' : 'send'}</span>
            </button>
          </div>
        </div>
      </div>

      {/* Outcome Gauge */}
      <div className="glass-panel border border-surface-border rounded-xl p-5 shadow-lg relative overflow-hidden bg-gradient-to-br from-surface-dark to-primary/5 group hover:border-primary/30 transition-all duration-500">
        <div className="absolute -right-12 -top-12 size-40 bg-primary/10 rounded-full blur-3xl group-hover:bg-primary/20 transition-all duration-700"></div>
        <div className="flex items-start justify-between z-10 relative mb-4">
          <h3 className="text-xs uppercase text-text-secondary font-bold tracking-widest">{t('predicted_outcome')}</h3>
          <span className="text-[10px] text-primary font-mono border border-primary/30 px-1.5 py-0.5 rounded bg-primary/5">{t('confidence_short')}: 92%</span>
        </div>
        <div className="flex items-center gap-6 z-10 relative">
          <div className="relative size-24 flex-shrink-0 group-hover:scale-105 transition-transform duration-500">
            <svg className="size-full rotate-[135deg]" viewBox="0 0 100 100">
              <circle className="text-surface-border" cx="50" cy="50" fill="transparent" r="40" stroke="currentColor" strokeWidth="8"></circle>
              <circle className="text-primary drop-shadow-[0_0_8px_rgba(19,127,236,0.5)]" cx="50" cy="50" fill="transparent" r="40" stroke="currentColor" strokeDasharray="251.2" strokeDashoffset="62.8" strokeLinecap="round" strokeWidth="8"></circle>
            </svg>
            <div className="absolute inset-0 flex flex-col items-center justify-center">
              <span className="text-2xl font-bold text-white tracking-tight">88<span className="text-sm">%</span></span>
              <span className="text-[8px] text-text-secondary uppercase">{t('yield')}</span>
            </div>
          </div>
          <div className="flex-1 space-y-3">
            <div className="flex justify-between items-center text-xs">
              <span className="text-text-secondary">{t('target')}</span>
              <span className="text-white font-mono font-bold">&gt;90%</span>
            </div>
            <div className="flex justify-between items-center text-xs">
              <span className="text-text-secondary">{t('variance')}</span>
              <span className="text-status-warning flex items-center gap-1 font-mono font-bold">
                <span className="material-symbols-outlined text-[10px]">trending_down</span>
                -2.1%
              </span>
            </div>
            <button className="w-full bg-white text-background-dark hover:bg-gray-200 font-bold text-xs py-2 rounded shadow-[0_0_10px_rgba(255,255,255,0.2)] transition-all flex items-center justify-center gap-1 cursor-pointer active:scale-95">
              <span className="material-symbols-outlined text-sm">verified</span>
              {t('confirm')}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
});

export default AICopilot;