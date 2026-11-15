import { createI18n } from 'vue-i18n';
import messages from './locale';

export function createAppI18n(locale: App.I18n.LangType = 'zh-CN') {
  return createI18n({
    locale,
    fallbackLocale: 'en-US',
    messages,
    legacy: false
  });
}
