import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import zhCN from './locales/zh-CN.json';
import en from './locales/en.json';

export type Language = 'zh-CN' | 'en';

export const LANGUAGE_STORAGE_KEY = 'ske-lang';

export function detectLanguage(): Language {
  try {
    const saved = localStorage.getItem(LANGUAGE_STORAGE_KEY);
    if (saved === 'zh-CN' || saved === 'en') return saved;
  } catch {
    /* ignore unavailable storage */
  }
  // 本项目面向中国法律知识环境，默认简体中文；可随时切换英文。
  return 'zh-CN';
}

export function setLanguage(lang: Language) {
  try {
    localStorage.setItem(LANGUAGE_STORAGE_KEY, lang);
  } catch {
    /* ignore */
  }
  void i18n.changeLanguage(lang);
}

i18n.use(initReactI18next).init({
  resources: {
    'zh-CN': { translation: zhCN },
    en: { translation: en },
  },
  lng: detectLanguage(),
  fallbackLng: 'zh-CN',
  interpolation: { escapeValue: false },
});

export default i18n;
