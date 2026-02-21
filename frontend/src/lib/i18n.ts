import { useState, useCallback } from 'react';

const translations = {
  zh: {
    title: '提钒冶炼智能体 VEES v7.0',
    subtitle: 'VANADIUM EXTRACTION EXPERT SYSTEM',
    l1_title: 'L1: 静态设定',
    l2_title: 'L2: 动态监测',
    l3_title: 'L3: AI 辅助决策',
    // ... add more as needed
  },
  en: {
    title: 'VEES v7.0 Industrial Agent',
    subtitle: 'VANADIUM EXTRACTION EXPERT SYSTEM',
    l1_title: 'L1: STATIC SETUP',
    l2_title: 'L2: DYNAMIC MONITOR',
    l3_title: 'L3: AI CO-PILOT',
    // ... add more as needed
  }
};

export function useI18n() {
  const [lang, setLang] = useState<'zh' | 'en'>('zh');

  const t = useCallback((key: string) => {
    return translations[lang][key] || key;
  }, [lang]);

  return { t, lang, setLang };
}
