import React, { useState, useRef, useEffect, useCallback, useMemo } from 'react';
import { chatWithAgent } from '../src/lib/mcp';
import { useLanguage } from '../src/contexts/LanguageContext';

interface Props {
  processContext: any;
}

interface CopilotMessage {
  id: string;
  type: 'user' | 'recommendation' | 'warning';
  content: string;
  timestamp: string;
  traceId?: string;
  collaborationMeta?: {
    mode?: string;
    agents_involved?: string[];
    safe_mode_active?: boolean;
    safe_mode_reasons?: string[];
  };
}

interface ChatResponse {
  reply: string;
  trace_id?: string;
  collaboration_meta?: {
    mode?: string;
    agents_involved?: string[];
    safe_mode_active?: boolean;
    safe_mode_reasons?: string[];
  };
}

interface AgentCardData {
  name: string;
  role: string;
  action: string;
  confidence: number;
  active: boolean;
}

const AICopilot: React.FC<Props> = React.memo(({ processContext }) => {
  const FAB_SIZE = 56;
  const PANEL_MAX_WIDTH = 448;
  const PANEL_MAX_HEIGHT = 620;
  const PANEL_WIDTH_RATIO = 0.92;
  const PANEL_HEIGHT_RATIO = 0.72;
  const EDGE_GAP = 16;
  const { t } = useLanguage();
  const [isOpen, setIsOpen] = useState(false);
  const [chatInput, setChatInput] = useState('');
  const [floatingPos, setFloatingPos] = useState<{ x: number; y: number } | null>(null);
  const [messages, setMessages] = useState<CopilotMessage[]>([
    {
      id: '1',
      type: 'recommendation',
      content: t('ai_welcome'),
      timestamp: new Date().toLocaleTimeString(),
    }
  ]);
  const [isLoading, setIsLoading] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const dragMetaRef = useRef<{ offsetX: number; offsetY: number; width: number; height: number } | null>(null);
  const dragMovedRef = useRef(false);
  const [isDragging, setIsDragging] = useState(false);
  const panelWidth = typeof window === 'undefined' ? PANEL_MAX_WIDTH : Math.min(window.innerWidth * PANEL_WIDTH_RATIO, PANEL_MAX_WIDTH);
  const panelHeight = typeof window === 'undefined' ? PANEL_MAX_HEIGHT : Math.min(window.innerHeight * PANEL_HEIGHT_RATIO, PANEL_MAX_HEIGHT);
  const activeWidth = isOpen ? panelWidth : FAB_SIZE;
  const activeHeight = isOpen ? panelHeight : FAB_SIZE;
  const clampPosition = useCallback((x: number, y: number, width: number, height: number) => {
    if (typeof window === 'undefined') {
      return { x, y };
    }
    const maxX = Math.max(EDGE_GAP, window.innerWidth - width - EDGE_GAP);
    const maxY = Math.max(EDGE_GAP, window.innerHeight - height - EDGE_GAP);
    return {
      x: Math.min(Math.max(EDGE_GAP, x), maxX),
      y: Math.min(Math.max(EDGE_GAP, y), maxY)
    };
  }, []);
  const latestCollaborationMeta = useMemo(
    () => [...messages].reverse().find((msg) => !!msg.collaborationMeta)?.collaborationMeta,
    [messages]
  );
  const defaultAgentPool = useMemo(
    () => ['协调中枢', '工艺优化', '安全护栏', '质量复核'],
    []
  );
  const activeAgents = latestCollaborationMeta?.agents_involved?.length
    ? latestCollaborationMeta.agents_involved
    : defaultAgentPool;
  const agentRoster = useMemo(
    () => Array.from(new Set([...defaultAgentPool, ...activeAgents])).slice(0, 6),
    [activeAgents, defaultAgentPool]
  );
  const agentCardMeta = useMemo(() => ({
    协调中枢: {
      role: t('agent_role_coordinator'),
      action: t('agent_action_coordinator')
    },
    工艺优化: {
      role: t('agent_role_process'),
      action: t('agent_action_process')
    },
    安全护栏: {
      role: t('agent_role_safety'),
      action: t('agent_action_safety')
    },
    质量复核: {
      role: t('agent_role_quality'),
      action: t('agent_action_quality')
    }
  }), [t]);
  const agentCards = useMemo<AgentCardData[]>(() => (
    agentRoster.map((agentName, index) => {
      const active = activeAgents.includes(agentName);
      const meta = agentCardMeta[agentName as keyof typeof agentCardMeta] || {
        role: t('agent_role_generic'),
        action: t('agent_action_generic')
      };
      const baseConfidence = latestCollaborationMeta?.safe_mode_active ? 0.78 : 0.92;
      const confidence = active ? Math.max(0.7, baseConfidence - index * 0.03) : Math.max(0.62, baseConfidence - 0.2 - index * 0.02);
      return {
        name: agentName,
        role: meta.role,
        action: meta.action,
        confidence,
        active
      };
    })
  ), [activeAgents, agentCardMeta, agentRoster, latestCollaborationMeta?.safe_mode_active, t]);

  useEffect(() => {
    if (scrollRef.current) {
      const scrollOptions: ScrollToOptions = {
        top: scrollRef.current.scrollHeight,
        behavior: 'smooth'
      };
      scrollRef.current.scrollTo(scrollOptions);
    }
  }, [messages]);
  useEffect(() => {
    if (typeof window === 'undefined') {
      return;
    }
    const initial = clampPosition(window.innerWidth - activeWidth - 24, window.innerHeight - activeHeight - 24, activeWidth, activeHeight);
    setFloatingPos((prev) => prev ?? initial);
  }, [activeHeight, activeWidth, clampPosition]);

  useEffect(() => {
    if (typeof window === 'undefined') {
      return;
    }
    const handleResize = () => {
      setFloatingPos((prev) => {
        if (!prev) {
          const initial = clampPosition(window.innerWidth - activeWidth - 24, window.innerHeight - activeHeight - 24, activeWidth, activeHeight);
          return initial;
        }
        return clampPosition(prev.x, prev.y, activeWidth, activeHeight);
      });
    };
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, [activeHeight, activeWidth, clampPosition]);

  const startDrag = useCallback((clientX: number, clientY: number) => {
    if (!floatingPos) {
      return;
    }
    dragMetaRef.current = {
      offsetX: clientX - floatingPos.x,
      offsetY: clientY - floatingPos.y,
      width: activeWidth,
      height: activeHeight
    };
    dragMovedRef.current = false;
    setIsDragging(true);
  }, [activeHeight, activeWidth, floatingPos]);

  const moveDrag = useCallback((clientX: number, clientY: number) => {
    if (!dragMetaRef.current) {
      return;
    }
    const nextX = clientX - dragMetaRef.current.offsetX;
    const nextY = clientY - dragMetaRef.current.offsetY;
    const clamped = clampPosition(nextX, nextY, dragMetaRef.current.width, dragMetaRef.current.height);
    const previous = floatingPos ?? clamped;
    const movement = Math.abs(clamped.x - previous.x) + Math.abs(clamped.y - previous.y);
    if (movement > 2) {
      dragMovedRef.current = true;
    }
    setFloatingPos(clamped);
  }, [clampPosition, floatingPos]);

  const endDrag = useCallback(() => {
    dragMetaRef.current = null;
    setIsDragging(false);
  }, []);

  useEffect(() => {
    const onMove = (e: PointerEvent) => moveDrag(e.clientX, e.clientY);
    const onUp = () => endDrag();
    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onUp);
    return () => {
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', onUp);
    };
  }, [endDrag, moveDrag]);

  const floatingStyle = floatingPos
    ? { left: `${floatingPos.x}px`, top: `${floatingPos.y}px` }
    : undefined;

  const handleSend = useCallback(async () => {
    if (!chatInput.trim() || isLoading) return;
    
    const currentInput = chatInput;
    setChatInput('');
    setIsLoading(true);
    setIsOpen(true);

    const userMsg: CopilotMessage = {
      id: Date.now().toString(),
      type: 'user',
      content: currentInput,
      timestamp: new Date().toLocaleTimeString(),
    };
    
    setMessages(prev => [...prev, userMsg]);

    try {
      const res = await chatWithAgent(currentInput, processContext) as ChatResponse;
      const aiMsg: CopilotMessage = {
        id: (Date.now() + 1).toString(),
        type: 'recommendation',
        content: res.reply,
        timestamp: new Date().toLocaleTimeString(),
        traceId: res.trace_id,
        collaborationMeta: res.collaboration_meta
      };
      setMessages(prev => [...prev, aiMsg]);
      setTimeout(() => setIsOpen(false), 1200);
    } catch (e) {
      console.error("Chat error:", e);
      const warningMsg: CopilotMessage = {
        id: (Date.now() + 1).toString(),
        type: 'warning',
        content: t('ai_connect_fail'),
        timestamp: new Date().toLocaleTimeString(),
      };
      setMessages(prev => [...prev, warningMsg]);
      setTimeout(() => setIsOpen(false), 1200);
    } finally {
      setIsLoading(false);
    }
  }, [chatInput, isLoading, processContext, t]);

  if (!isOpen) {
    return (
      <button
        onClick={() => {
          if (dragMovedRef.current) {
            dragMovedRef.current = false;
            return;
          }
          setIsOpen(true);
        }}
        onPointerDown={(e) => {
          startDrag(e.clientX, e.clientY);
        }}
        aria-label={t('ai_copilot_title')}
        style={floatingStyle}
        className={`fixed z-50 size-14 rounded-full bg-gradient-to-br from-indigo-500 to-purple-600 text-white shadow-[0_0_24px_rgba(129,140,248,0.55)] hover:shadow-[0_0_30px_rgba(147,51,234,0.6)] transition-all duration-200 cursor-grab active:cursor-grabbing flex items-center justify-center ${isDragging ? 'scale-105' : ''}`}
      >
        <span className="material-symbols-outlined">smart_toy</span>
      </button>
    );
  }

  return (
    <div
      style={{ ...floatingStyle, width: panelWidth, height: panelHeight }}
      className="fixed z-50 rounded-2xl overflow-hidden border border-purple-500/30 bg-surface-dark shadow-2xl"
    >
      <div className="h-full flex flex-col">
        <div
          onPointerDown={(e) => startDrag(e.clientX, e.clientY)}
          className="p-4 border-b border-surface-border bg-surface-dark flex items-center justify-between gap-3 cursor-grab active:cursor-grabbing"
        >
          <div className="flex items-center gap-3 min-w-0">
            <div className="relative">
              <div className="size-9 rounded-full bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center shadow-[0_0_10px_theme('colors.purple.500')]">
                <span className="material-symbols-outlined text-white text-lg">auto_awesome</span>
              </div>
              <div className="absolute -bottom-0.5 -right-0.5 size-2.5 bg-status-safe border-2 border-surface-dark rounded-full animate-pulse"></div>
            </div>
            <div className="min-w-0">
              <h3 className="text-sm font-bold text-white truncate">{t('ai_copilot_title')}</h3>
              <p className="text-[10px] text-text-secondary flex items-center gap-1">
                <span className="material-symbols-outlined text-[10px] animate-pulse">bolt</span>
                Kinetic-V7.2
              </p>
            </div>
          </div>
          <button
            onClick={() => setIsOpen(false)}
            onPointerDown={(e) => e.stopPropagation()}
            aria-label="Close AI Copilot"
            className="size-8 rounded-lg border border-surface-border text-text-secondary hover:text-white hover:border-purple-400 transition-colors cursor-pointer flex items-center justify-center"
          >
            <span className="material-symbols-outlined text-base">close</span>
          </button>
        </div>
        <div className="px-4 py-3 border-b border-surface-border/70 bg-[#0b1116]/80">
          <div className="flex items-center justify-between gap-2 mb-2">
            <span className="text-[10px] uppercase tracking-[0.18em] text-text-secondary font-bold">{t('agent_hub_title')}</span>
            <span className={`text-[10px] font-mono px-2 py-0.5 rounded border ${
              latestCollaborationMeta?.safe_mode_active
                ? 'text-status-warning border-status-warning/40 bg-status-warning/10'
                : 'text-status-safe border-status-safe/40 bg-status-safe/10'
            }`}>
              {latestCollaborationMeta?.safe_mode_active ? t('safe_mode_on') : t('agent_network_ready')}
            </span>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            {agentCards.map((agent) => {
              return (
                <div
                  key={agent.name}
                  className={`rounded-lg border px-2.5 py-2 transition-all ${
                    agent.active
                      ? 'border-primary/40 bg-primary/10 text-white shadow-[0_0_14px_rgba(19,127,236,0.12)]'
                      : 'border-surface-border/60 bg-surface-dark/40 text-text-secondary'
                  }`}
                >
                  <div className="flex items-center justify-between gap-2 mb-1.5">
                    <div className="flex items-center gap-2 min-w-0">
                      <span className={`size-2 rounded-full ${agent.active ? 'bg-status-safe shadow-[0_0_8px_rgba(34,197,94,0.8)]' : 'bg-surface-border'}`}></span>
                      <span className="text-[11px] font-semibold tracking-wide truncate">{agent.name}</span>
                    </div>
                    <span className={`text-[10px] font-mono px-1.5 py-0.5 rounded border ${agent.active ? 'text-primary border-primary/40 bg-primary/10' : 'text-text-secondary border-surface-border/60 bg-surface-dark/60'}`}>
                      {(agent.confidence * 100).toFixed(0)}%
                    </span>
                  </div>
                  <div className="space-y-1">
                    <div className="text-[10px] text-text-secondary">
                      {t('agent_role_label')}: <span className={agent.active ? 'text-white' : 'text-text-secondary'}>{agent.role}</span>
                    </div>
                    <div className="text-[10px] text-text-secondary">
                      {t('agent_last_action_label')}: <span className={agent.active ? 'text-white' : 'text-text-secondary'}>{agent.action}</span>
                    </div>
                    <div className="text-[10px] text-text-secondary">
                      {t('agent_confidence_label')}:
                      <div className="mt-1 h-1.5 rounded-full bg-surface-border/60 overflow-hidden">
                        <div
                          className={`h-full rounded-full transition-all duration-300 ${agent.active ? 'bg-primary' : 'bg-text-secondary/70'}`}
                          style={{ width: `${Math.max(8, Math.round(agent.confidence * 100))}%` }}
                        ></div>
                      </div>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

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
                  {msg.collaborationMeta && (
                    <div className="mt-2 pt-2 border-t border-white/10 text-[9px] text-text-secondary font-mono space-y-1">
                      <div className="flex items-center gap-1">
                        <span className="material-symbols-outlined text-[10px]">hub</span>
                        <span>{t('collaboration_mode')}: {msg.collaborationMeta.mode === 'multi_agent' ? t('multi_agent_mode') : (msg.collaborationMeta.mode || '-')}</span>
                      </div>
                      <div className="flex items-center gap-1">
                        <span className="material-symbols-outlined text-[10px]">shield</span>
                        <span>{t('safe_mode_status')}: {msg.collaborationMeta.safe_mode_active ? t('safe_mode_on') : t('safe_mode_off')}</span>
                      </div>
                      {!!msg.collaborationMeta.agents_involved?.length && (
                        <div className="flex items-start gap-1">
                          <span className="material-symbols-outlined text-[10px] mt-[1px]">groups</span>
                          <span className="pt-[1px]">{t('agents_involved')}:</span>
                          <div className="flex flex-wrap gap-1">
                            {msg.collaborationMeta.agents_involved.map((agentName) => (
                              <span key={`${msg.id}-${agentName}`} className="px-1.5 py-0.5 rounded border border-primary/30 bg-primary/10 text-primary">
                                {agentName}
                              </span>
                            ))}
                          </div>
                        </div>
                      )}
                      {!!msg.collaborationMeta.safe_mode_reasons?.length && (
                        <div className="flex items-start gap-1 text-status-warning">
                          <span className="material-symbols-outlined text-[10px] mt-[1px]">error</span>
                          <span>{t('degradation_reason')}: {msg.collaborationMeta.safe_mode_reasons.join('；')}</span>
                        </div>
                      )}
                    </div>
                  )}
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
    </div>
  );
});

export default AICopilot;
