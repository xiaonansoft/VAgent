import React, { useState, useEffect } from 'react';
import { useLanguage } from '../contexts/LanguageContext';

type SystemMode = 'SIMULATION' | 'VALIDATION' | 'PRODUCTION';

interface ModeInfo {
  mode: SystemMode;
  labelKey: string;
  descKey: string;
  color: string;
  icon: string;
  requiresToken: boolean;
}

const Settings: React.FC = () => {
  const { t } = useLanguage();
  const [currentMode, setCurrentMode] = useState<SystemMode>('SIMULATION');
  const [targetMode, setTargetMode] = useState<SystemMode | null>(null);
  const [token, setToken] = useState('');
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const [showModal, setShowModal] = useState(false);

  useEffect(() => {
    fetchMode();
  }, []);

  const fetchMode = async () => {
    try {
      const res = await fetch('/api/system/mode');
      const data = await res.json();
      setCurrentMode(data.mode);
    } catch (err) {
      console.error("Failed to fetch mode", err);
    }
  };

  const modes: ModeInfo[] = [
    {
      mode: 'SIMULATION',
      labelKey: 'mode_simulation',
      descKey: 'mode_simulation_desc',
      color: 'bg-status-safe',
      icon: 'science',
      requiresToken: false
    },
    {
      mode: 'VALIDATION',
      labelKey: 'mode_validation',
      descKey: 'mode_validation_desc',
      color: 'bg-status-warning',
      icon: 'visibility',
      requiresToken: false
    },
    {
      mode: 'PRODUCTION',
      labelKey: 'mode_production',
      descKey: 'mode_production_desc',
      color: 'bg-status-alarm',
      icon: 'factory',
      requiresToken: true
    }
  ];

  const handleModeClick = (mode: SystemMode) => {
    if (mode === currentMode) return;
    setTargetMode(mode);
    setToken('');
    setShowModal(true);
    setMessage(null);
  };

  const confirmSwitch = async () => {
    if (!targetMode) return;
    setLoading(true);
    setMessage(null);

    try {
      const res = await fetch('/api/system/mode', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          mode: targetMode,
          token: token || 'default', // Backend expects some string even if not prod
          user: 'ui_user'
        })
      });

      if (!res.ok) {
        const errorData = await res.json();
        throw new Error(errorData.detail || t('mode_switch_error'));
      }

      const data = await res.json();
      setCurrentMode(data.mode);
      setMessage({ type: 'success', text: t('mode_switch_success') || 'Mode switched successfully' });
      setShowModal(false);
    } catch (err: any) {
      setMessage({ type: 'error', text: err.message });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex-1 overflow-auto p-8 text-white h-full bg-[#0b1116]">
      <div className="max-w-4xl mx-auto">
        <h1 className="text-3xl font-bold mb-8 flex items-center gap-3">
          <span className="material-symbols-outlined text-4xl text-primary">settings</span>
          {t('settings_title') || 'System Settings'}
        </h1>

        {/* Current Mode Banner */}
        <div className="mb-10 bg-surface-dark border border-surface-border rounded-xl p-6 flex items-center justify-between shadow-lg relative overflow-hidden">
          <div className={`absolute top-0 left-0 w-2 h-full ${
            currentMode === 'SIMULATION' ? 'bg-status-safe' : 
            currentMode === 'VALIDATION' ? 'bg-status-warning' : 'bg-status-alarm'
          }`}></div>
          <div>
            <h2 className="text-sm uppercase tracking-wider text-text-secondary mb-1">{t('current_mode') || 'Current Mode'}</h2>
            <div className="text-2xl font-mono font-bold flex items-center gap-3">
              {currentMode}
              <span className={`px-2 py-0.5 rounded text-xs font-bold text-black ${
                 currentMode === 'SIMULATION' ? 'bg-status-safe' : 
                 currentMode === 'VALIDATION' ? 'bg-status-warning' : 'bg-status-alarm'
              }`}>ACTIVE</span>
            </div>
          </div>
          <span className="material-symbols-outlined text-6xl opacity-10">
             {currentMode === 'SIMULATION' ? 'science' : 
              currentMode === 'VALIDATION' ? 'visibility' : 'factory'}
          </span>
        </div>

        {/* Mode Selection Grid */}
        <h3 className="text-xl font-semibold mb-6 text-white/90 border-l-4 border-primary pl-3">{t('mode_selection') || 'Operation Mode Selection'}</h3>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {modes.map((m) => (
            <div 
              key={m.mode}
              onClick={() => handleModeClick(m.mode)}
              className={`
                relative group cursor-pointer rounded-xl border p-6 transition-all duration-300
                ${currentMode === m.mode 
                  ? 'bg-surface-dark border-white/20 shadow-neon-blue' 
                  : 'bg-surface-dark/50 border-surface-border hover:bg-surface-dark hover:border-primary/50 hover:-translate-y-1'
                }
              `}
            >
              <div className={`
                w-12 h-12 rounded-lg flex items-center justify-center mb-4 text-black font-bold shadow-lg
                ${m.color}
              `}>
                <span className="material-symbols-outlined text-2xl">{m.icon}</span>
              </div>
              <h3 className="text-lg font-bold mb-2 text-white group-hover:text-primary transition-colors">
                {t(m.labelKey as any) || m.mode}
              </h3>
              <p className="text-sm text-text-secondary leading-relaxed">
                {t(m.descKey as any)}
              </p>
              
              {currentMode === m.mode && (
                <div className="absolute top-4 right-4 text-status-safe">
                  <span className="material-symbols-outlined">check_circle</span>
                </div>
              )}
            </div>
          ))}
        </div>

        {/* Feedback Message */}
        {message && !showModal && (
           <div className={`mt-6 p-4 rounded-lg flex items-center gap-3 ${
             message.type === 'success' ? 'bg-status-safe/10 border border-status-safe/30 text-status-safe' : 'bg-status-alarm/10 border border-status-alarm/30 text-status-alarm'
           }`}>
             <span className="material-symbols-outlined">{message.type === 'success' ? 'check_circle' : 'error'}</span>
             {message.text}
           </div>
        )}
      </div>

      {/* Confirmation Modal */}
      {showModal && targetMode && (
        <div className="fixed inset-0 bg-black/80 backdrop-blur-sm flex items-center justify-center z-50 p-4">
          <div className="bg-[#1A2634] border border-surface-border rounded-2xl w-full max-w-md shadow-2xl transform transition-all scale-100">
            <div className="p-6">
              <h3 className="text-xl font-bold mb-4 flex items-center gap-2 text-white">
                <span className="material-symbols-outlined text-primary">sync_alt</span>
                {t('confirm_switch') || 'Confirm Mode Switch'}
              </h3>
              <p className="text-text-secondary mb-6">
                {(t('confirm_switch_msg') || 'Are you sure you want to switch to {mode}?').replace('{mode}', targetMode)}
              </p>

              {modes.find(m => m.mode === targetMode)?.requiresToken && (
                <div className="mb-6">
                  <label className="block text-xs font-bold uppercase text-text-secondary mb-2 tracking-wider">
                    {t('auth_token') || 'Authorization Token'}
                  </label>
                  <input 
                    type="password"
                    value={token}
                    onChange={(e) => setToken(e.target.value)}
                    className="w-full bg-black/20 border border-surface-border rounded-lg px-4 py-3 text-white focus:outline-none focus:border-primary transition-colors font-mono"
                    placeholder={t('enter_token') || 'Enter security token'}
                    autoFocus
                  />
                  <p className="text-xs text-text-secondary mt-2">
                    * Production mode requires a valid security token (Try: SECURE_PRODUCTION_TOKEN_2026)
                  </p>
                </div>
              )}

              {/* In-modal Error Message */}
              {message && message.type === 'error' && (
                <div className="mb-4 p-3 rounded bg-status-alarm/10 border border-status-alarm/30 text-status-alarm text-sm flex items-center gap-2 animate-pulse">
                  <span className="material-symbols-outlined text-sm">error</span>
                  {message.text}
                </div>
              )}

              <div className="flex gap-3 justify-end mt-8">
                <button 
                  onClick={() => setShowModal(false)}
                  className="px-4 py-2 rounded-lg text-text-secondary hover:bg-white/5 transition-colors font-medium text-sm border border-transparent hover:border-white/10"
                  disabled={loading}
                >
                  {t('cancel') || 'Cancel'}
                </button>
                <button 
                  onClick={confirmSwitch}
                  disabled={loading}
                  className={`
                    px-6 py-2 rounded-lg font-bold text-sm shadow-lg flex items-center gap-2 transition-all
                    ${loading ? 'bg-gray-600 cursor-not-allowed opacity-70' : 'bg-primary hover:bg-blue-600 text-white hover:shadow-primary/30'}
                  `}
                >
                  {loading && <span className="w-3 h-3 border-2 border-white/30 border-t-white rounded-full animate-spin"></span>}
                  {t('confirm') || 'Confirm'}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default Settings;
