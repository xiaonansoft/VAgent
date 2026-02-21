import React from 'react';
import { useProcessStream } from '../src/hooks/useProcessStream';
import { useLanguage } from '../src/contexts/LanguageContext';
import { Link, useLocation } from 'react-router-dom';

const Header: React.FC = () => {
  const { isConnected, data } = useProcessStream();
  const { t, language, setLanguage } = useLanguage();
  const location = useLocation();

  const isEmergencyStop = data?.is_emergency_stop || false;

  const handleStop = async () => {
    try {
      if (isEmergencyStop) {
        await fetch('/api/mcp/data', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            jsonrpc: "2.0",
            method: "control/resume",
            id: 1
          })
        });
      } else {
        await fetch('/api/mcp/data', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            jsonrpc: "2.0",
            method: "control/stop",
            id: 1
          })
        });
      }
    } catch (e) {
      console.error("Failed to toggle stop", e);
    }
  };

  const toggleLanguage = () => {
    setLanguage(language === 'zh' ? 'en' : 'zh');
  };

  const toggleFullScreen = () => {
    if (!document.fullscreenElement) {
      document.documentElement.requestFullscreen().catch(err => {
        console.error(`Error attempting to enable full-screen mode: ${err.message} (${err.name})`);
      });
    } else {
      if (document.exitFullscreen) {
        document.exitFullscreen();
      }
    }
  };

  const isActive = (path: string) => location.pathname === path;

  return (
    <header className="flex items-center justify-between whitespace-nowrap border-b border-surface-border px-4 lg:px-6 py-3 bg-surface-dark/80 backdrop-blur-md z-50 overflow-x-hidden">
      {/* Left Section: Logo & Status */}
      <div className="flex items-center gap-3 lg:gap-6 text-white shrink-0">
        <div className="flex items-center gap-3">
          <div className="size-9 bg-gradient-to-br from-primary to-blue-600 rounded flex items-center justify-center text-white shadow-neon-blue shrink-0">
            <span className="material-symbols-outlined">factory</span>
          </div>
          <div className="hidden sm:block">
            <h2 className="text-white text-lg font-bold leading-tight tracking-wide">VAgent</h2>
            <div className="flex items-center gap-2 mt-0.5">
              <span className="relative flex size-2">
                <span className={`animate-ping absolute inline-flex h-full w-full rounded-full opacity-75 ${isConnected ? 'bg-status-safe' : 'bg-status-alarm'}`}></span>
                <span className={`relative inline-flex rounded-full size-2 ${isConnected ? 'bg-status-safe' : 'bg-status-alarm'}`}></span>
              </span>
              <span className={`text-[10px] font-bold uppercase tracking-wider ${isConnected ? 'text-status-safe' : 'text-status-alarm'}`}>
                {isConnected ? t('system_online') : t('system_offline')}
              </span>
            </div>
          </div>
        </div>
        
        {/* Navigation */}
        <nav className="hidden md:flex items-center gap-4 ml-2 border-l border-surface-border/50 pl-4 lg:pl-6">
          <Link 
            to="/" 
            className={`text-sm font-medium transition-colors ${isActive('/') ? 'text-primary' : 'text-text-secondary hover:text-white'}`}
          >
            {t('nav_dashboard')}
          </Link>
          <Link 
            to="/history" 
            className={`text-sm font-medium transition-colors ${isActive('/history') ? 'text-primary' : 'text-text-secondary hover:text-white'}`}
          >
            {t('nav_history')}
          </Link>
          <Link 
            to="/learning" 
            className={`text-sm font-medium transition-colors ${isActive('/learning') ? 'text-primary' : 'text-text-secondary hover:text-white'}`}
          >
            {t('nav_learning')}
          </Link>
          <Link 
            to="/settings" 
            className={`text-sm font-medium transition-colors ${isActive('/settings') ? 'text-primary' : 'text-text-secondary hover:text-white'}`}
          >
            {t('nav_settings')}
          </Link>
        </nav>
      </div>

      {/* Center Section: Metadata */}
      <div className="flex flex-1 justify-center hidden lg:flex px-4">
        <div className="flex gap-6 bg-surface-dark/50 px-6 py-1.5 rounded-full border border-surface-border/50 whitespace-nowrap">
          <div className="flex flex-col items-center">
            <span className="text-[9px] text-text-secondary uppercase tracking-widest">{t('furnace')}</span>
            <span className="text-xs font-bold text-white">{t('converter_3')}</span>
          </div>
          <div className="w-px h-full bg-surface-border/50"></div>
          <div className="flex flex-col items-center">
            <span className="text-[9px] text-text-secondary uppercase tracking-widest">{t('shift')}</span>
            <span className="text-xs font-bold text-white">{t('team_a_night')}</span>
          </div>
          <div className="w-px h-full bg-surface-border/50"></div>
          <div className="flex flex-col items-center">
            <span className="text-[9px] text-text-secondary uppercase tracking-widest">{t('uptime')}</span>
            <span className="text-xs font-bold font-mono text-primary">142h 12m</span>
          </div>
        </div>
      </div>

      {/* Right Section: Actions */}
      <div className="flex items-center gap-2 lg:gap-4 shrink-0">
        <div className="relative hidden xl:block group">
          <span className="material-symbols-outlined absolute left-3 top-1/2 -translate-y-1/2 text-text-secondary text-lg group-focus-within:text-primary transition-colors">search</span>
          <input className="bg-[#0b1116] border border-surface-border rounded-full py-1.5 pl-9 pr-4 text-xs text-white focus:ring-1 focus:ring-primary focus:border-primary placeholder-gray-600 w-32 lg:w-48 transition-all focus:w-64" placeholder={t('search_placeholder')} type="text" />
        </div>
        <div className="flex gap-2">
          <button 
            className="flex items-center justify-center rounded-lg h-9 px-3 bg-surface-border/30 border border-surface-border text-text-secondary hover:bg-primary/20 hover:text-white hover:border-primary/50 transition-all text-xs font-medium gap-1.5 cursor-pointer" 
            title="Switch Language"
            aria-label="Switch Language"
            onClick={toggleLanguage}
          >
            <span className="material-symbols-outlined text-[18px]">language</span>
            <span>{language === 'zh' ? 'EN' : 'CN'}</span>
          </button>
          <button 
            className="flex items-center justify-center rounded-lg h-9 w-9 bg-surface-border/30 border border-surface-border text-text-secondary hover:bg-primary/20 hover:text-white hover:border-primary/50 transition-all cursor-pointer" 
            title="Full Screen"
            aria-label="Toggle Full Screen"
            onClick={toggleFullScreen}
          >
            <span className="material-symbols-outlined text-[20px]">fullscreen</span>
          </button>
          <button 
            className={`flex items-center justify-center rounded-lg h-9 px-4 border transition-all text-sm font-bold tracking-wide group cursor-pointer ${
              isEmergencyStop 
                ? 'bg-status-alarm text-white border-status-alarm animate-pulse' 
                : 'bg-status-alarm/10 border-status-alarm/20 text-status-alarm hover:bg-status-alarm hover:text-white hover:shadow-neon-amber'
            }`}
            aria-label="Emergency Stop"
            onClick={handleStop}
          >
            <span className="material-symbols-outlined text-[18px] mr-2 group-hover:animate-pulse">gpp_maybe</span>
            <span>{isEmergencyStop ? 'RESUME' : t('stop')}</span>
          </button>
          <div className="size-9 rounded-lg bg-cover bg-center border border-surface-border ring-2 ring-transparent hover:ring-primary transition-all cursor-pointer" style={{ backgroundImage: "url('https://lh3.googleusercontent.com/aida-public/AB6AXuD9nPL_Ynse3pWHyMHJZiwu3XhaUUfdftfZvllzvk40y1Vob7qgrHlgwDiLyFjytG6IuNLzJjp8HWvUBd9wGhB1DcjNqfZU8WNQsSvvrG7K7V0Tb9YxRsb_-89gEfRRnlryIQZUsnDvN0eFRlyhRyr-uUBciCFejN6-mV7k5K2Q4an6OWdyPGbg0qvcrTrbty17-d5XrpbmYAJvLR_cskmrn9CIJMaVxQLm0fGbZO5s6p6MvNgIINn-knBE6xLsIggsvkxjSEGt8IAp')" }}></div>
        </div>
      </div>
    </header>
  );
};

export default Header;
