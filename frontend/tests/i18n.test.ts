import assert from 'node:assert/strict';
import { test } from 'node:test';
import { createAppI18n } from '../src/locales/i18n';

test('loads the real Chinese catalog and switches to English', () => {
  const i18n = createAppI18n();
  assert.equal(i18n.global.t('common.cancel'), '取消');
  i18n.global.locale.value = 'en-US';
  assert.equal(i18n.global.t('common.cancel'), 'Cancel');
  assert.equal(i18n.global.t('system.title'), 'AgriGraph');
});

test('falls back to the registered English catalog for missing translations', () => {
  const i18n = createAppI18n();
  const chinese = { ...i18n.global.getLocaleMessage('zh-CN') };
  chinese.system = { ...chinese.system };
  Reflect.deleteProperty(chinese.system, 'title');
  i18n.global.setLocaleMessage('zh-CN', chinese);
  assert.equal(i18n.global.t('system.title', {}, {
    missingWarn: false, fallbackWarn: false
  }), 'AgriGraph');
});
