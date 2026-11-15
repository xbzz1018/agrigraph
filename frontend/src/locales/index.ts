import type { App } from 'vue';
import { localStg } from '@/utils/storage';
import { createAppI18n } from './i18n';

const i18n = createAppI18n(localStg.get('lang') || 'zh-CN');

/**
 * Setup plugin i18n
 *
 * @param app
 */
export function setupI18n(app: App) {
  app.use(i18n);
}

export const $t = i18n.global.t as App.I18n.$T;

export function setLocale(locale: App.I18n.LangType) {
  i18n.global.locale.value = locale;
}
