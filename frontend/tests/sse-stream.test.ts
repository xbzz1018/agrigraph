import assert from 'node:assert/strict';
import { test } from 'node:test';
import { readJsonSse } from '../src/utils/sse-stream';
import type { SseMessage } from '../src/utils/sse';

function streamOf(text: string, size = 1) {
  const bytes = new TextEncoder().encode(text);
  return new ReadableStream<Uint8Array>({
    start(controller) {
      for (let offset = 0; offset < bytes.length; offset += size) {
        controller.enqueue(bytes.slice(offset, offset + size));
      }
      controller.close();
    }
  });
}

for (const newline of ['\n', '\r\n', '\r']) {
  test(`parses ${JSON.stringify(newline)} lines across every byte boundary`, async () => {
    const text = [': heartbeat', 'event: answer', 'data: {"text":', 'data: "水稻"}', '',
      'data: {"done":true}', '', ''].join(newline);
    const messages: SseMessage[] = [];
    const stream = streamOf(text);
    await readJsonSse(stream, message => messages.push(message));
    assert.deepEqual(messages, [
      { event: 'answer', data: { text: '水稻' } },
      { event: 'message', data: { done: true } }
    ]);
    assert.equal(stream.locked, false);
  });
}

test('keeps complete events when a later event is unfinished at EOF', async () => {
  const messages: SseMessage[] = [];
  await readJsonSse(streamOf('data: 1\n\ndata: 2\n', 8), message => messages.push(message));
  assert.deepEqual(messages, [{ event: 'message', data: 1 }]);
});

test('removes exactly one optional field space and resets an empty event name', async () => {
  const messages: SseMessage[] = [];
  await readJsonSse(streamOf('event: answer \ndata: 1\n\nevent:\ndata: 2\n\n', 100), message => {
    messages.push(message);
  });
  assert.deepEqual(messages, [{ event: 'answer ', data: 1 }, { event: 'message', data: 2 }]);
});

for (const failure of ['invalid JSON', 'consumer error']) {
  test(`cancels the response and releases its reader on ${failure}`, async () => {
    let cancelled = false;
    const stream = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(new TextEncoder().encode(failure === 'invalid JSON' ? 'data: {\n\n' : 'data: 1\n\n'));
      },
      cancel() { cancelled = true; }
    });
    await assert.rejects(readJsonSse(stream, () => { throw new Error('consumer failed'); }));
    assert.equal(cancelled, true);
    assert.equal(stream.locked, false);
  });
}
