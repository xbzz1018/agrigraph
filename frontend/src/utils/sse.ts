import { getAuthorization } from '@/service/request/shared';

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

  const reader = response.body.getReader();
  const decoder = new TextDecoder('utf-8');
  let buffer = '';
  while (true) {
    const { value, done } = await reader.read();
    buffer += decoder.decode(value || new Uint8Array(), { stream: !done }).replace(/\r\n/g, '\n');
    // 网络分片可能截断一条事件，只有完整的空行分隔块才交给业务层。
    const blocks = buffer.split('\n\n');
    buffer = blocks.pop() || '';
    for (const block of blocks) {
      let event = 'message';
      const data: string[] = [];
      for (const line of block.split('\n')) {
        if (line.startsWith('event:')) event = line.slice(6).trim();
        if (line.startsWith('data:')) data.push(line.slice(5).trim());
      }
      if (!data.length) continue;
      const raw = data.join('\n');
      onMessage({ event, data: JSON.parse(raw) as T });
    }
    if (done) break;
  }
}
