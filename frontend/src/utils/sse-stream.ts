import type { SseMessage } from './sse';

/** Read JSON SSE events; an unfinished event at EOF is discarded. */
export async function readJsonSse<T>(
  stream: ReadableStream<Uint8Array>,
  onMessage: (message: SseMessage<T>) => void
) {
  const reader = stream.getReader();
  const decoder = new TextDecoder('utf-8');
  let line = '';
  let skipLf = false;
  let event = '';
  let data: string[] = [];

  function consumeLine() {
    if (!line) {
      if (data.length) onMessage({ event: event || 'message', data: JSON.parse(data.join('\n')) as T });
      event = '';
      data = [];
      return;
    }
    if (line.startsWith(':')) return;
    const colon = line.indexOf(':');
    const field = colon === -1 ? line : line.slice(0, colon);
    let value = colon === -1 ? '' : line.slice(colon + 1);
    if (value.startsWith(' ')) value = value.slice(1);
    if (field === 'event') event = value;
    if (field === 'data') data.push(value);
  }

  try {
    while (true) {
      const { value, done } = await reader.read();
      const text = decoder.decode(value, { stream: !done });
      for (const character of text) {
        // A CR dispatches the line immediately. Ignore its LF even across chunks.
        if (skipLf) {
          skipLf = false;
          if (character === '\n') continue;
        }
        if (character === '\r' || character === '\n') {
          consumeLine();
          line = '';
          skipLf = character === '\r';
        } else {
          line += character;
        }
      }
      if (done) break;
    }
  } finally {
    // A parser or consumer error must stop the response and release its lock.
    await reader.cancel().catch(() => undefined);
    reader.releaseLock();
  }
}
