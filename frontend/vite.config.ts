import process from 'node:process';
import { URL, fileURLToPath } from 'node:url';
import { defineConfig, loadEnv } from 'vite';
import { setupVitePlugins } from './build/plugins';
import { createViteProxy, getBuildTime } from './build/config';

export default defineConfig(configEnv => {
  const loadedEnv = Object.fromEntries(
    Object.entries(loadEnv(configEnv.mode, process.cwd())).filter(([, value]) => value !== '')
  );
  const viteEnv = {
    VITE_BASE_URL: '/',
    VITE_APP_TITLE: 'AgriGraph Evidence QA',
    VITE_APP_DESC: '农业 GraphRAG 证据问答系统',
    VITE_ICON_PREFIX: 'icon',
    VITE_ICON_LOCAL_PREFIX: 'icon-local',
    VITE_SERVICE_BASE_URL: 'http://127.0.0.1:8188/api/v1',
    VITE_SERVICE_SUCCESS_CODE: '200',
    VITE_SERVICE_LOGOUT_CODES: '401',
    VITE_SERVICE_MODAL_LOGOUT_CODES: '',
    VITE_SERVICE_EXPIRED_TOKEN_CODES: '401',
    VITE_OTHER_SERVICE_BASE_URL: '{}',
    VITE_AUTH_ROUTE_MODE: 'static',
    VITE_STATIC_SUPER_ROLE: 'ADMIN',
    VITE_ROUTE_HOME: 'chat',
    VITE_MENU_ICON: 'solar:menu-dots-linear',
    VITE_HTTP_PROXY: 'N',
    VITE_WS_TIMEOUT: '10000',
    ...loadedEnv
  } as unknown as Env.ImportMeta;
  const clientEnv = Object.fromEntries(
    Object.entries(viteEnv as unknown as Record<string, string>).map(([key, value]) => [
      `import.meta.env.${key}`,
      JSON.stringify(value)
    ])
  );

  const buildTime = getBuildTime();

  const enableProxy = configEnv.command === 'serve' && !configEnv.isPreview;

  return {
    base: viteEnv.VITE_BASE_URL,
    resolve: {
      alias: {
        '~': fileURLToPath(new URL('./', import.meta.url)),
        '@': fileURLToPath(new URL('./src', import.meta.url))
      }
    },
    css: {
      preprocessorOptions: {
        scss: {
          api: 'modern-compiler',
          additionalData: `@use "@/styles/scss/global.scss" as *;`
        }
      }
    },
    plugins: setupVitePlugins(viteEnv, buildTime),
    define: {
      ...clientEnv,
      BUILD_TIME: JSON.stringify(buildTime)
    },
    server: {
      host: '0.0.0.0',
      port: Number(viteEnv.VITE_PORT || 9627),
      open: true,
      proxy: createViteProxy(viteEnv, enableProxy),
      allowedHosts: ['u45964x883.zicp.vip']
    },
    preview: {
      port: Number(viteEnv.VITE_PREVIEW_PORT || 9725)
    },
    build: {
      reportCompressedSize: false,
      sourcemap: viteEnv.VITE_SOURCE_MAP === 'Y',
      commonjsOptions: {
        ignoreTryCatch: false
      }
    }
  };
});
