import { getAuthorization } from '@/service/request/shared';
import { readJsonSse } from './sse-stream';

export interface SseMessage<T = unknown> {
  event: string;
  data: T;
}

export async function postSse<T>(path: string, body: unknown, signal: AbortSignal,
                                 onMessage: (message: SseMessage<T>) => void) {
  // fetch 支持 POST 和 AbortSignal；原生 EventSource 无法满足这两个聊天接口要求。
  const base = String(import.meta.env.VITE_SERVICE_BASE_URL || '').replace(/\/$/, '');
  const response = await fetch(`${base}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: getAuthorization() || '' },
    body: JSON.stringify(body),
    signal
  });
  if (!response.ok || !response.body) throw new Error(`流式请求失败（HTTP ${response.status}）`);

  await readJsonSse(response.body, onMessage);
}
