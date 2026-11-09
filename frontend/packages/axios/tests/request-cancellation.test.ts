import assert from 'node:assert/strict';
import test from 'node:test';
import { CanceledError } from 'axios';
import type { AxiosAdapter, InternalAxiosRequestConfig } from 'axios';
import { REQUEST_ID_KEY, createRequest } from '../src/index';

function pendingAdapter() {
  let resolveStarted!: (config: InternalAxiosRequestConfig) => void;
  let rejectRequest!: (error: Error) => void;
  const started = new Promise<InternalAxiosRequestConfig>(resolve => {
    resolveStarted = resolve;
  });
  const stop = () => rejectRequest(new CanceledError('test cleanup'));
  const adapter: AxiosAdapter = config =>
    new Promise((_resolve, reject) => {
      rejectRequest = reject;
      (config.signal as AbortSignal).addEventListener('abort', stop, { once: true });
      resolveStarted(config);
    });
  return { adapter, started, stop };
}

for (const suppliedId of [undefined, 'supplied-request-id']) {
  test(`cancelRequest aborts only the selected request (${suppliedId ?? 'generated ID'})`, async () => {
    const request = createRequest();
    const first = pendingAdapter();
    const second = pendingAdapter();
    const results = [
      assert.rejects(
        request({ url: '/first', adapter: first.adapter, headers: suppliedId ? { [REQUEST_ID_KEY]: suppliedId } : {} }),
        { code: 'ERR_CANCELED' }
      ),
      assert.rejects(request({ url: '/second', adapter: second.adapter }), { code: 'ERR_CANCELED' })
    ];
    const [firstConfig, secondConfig] = await Promise.all([first.started, second.started]);
    try {
      const requestId = firstConfig.headers.get(REQUEST_ID_KEY) as string;
      assert.ok(requestId);
      assert.notEqual(requestId, secondConfig.headers.get(REQUEST_ID_KEY));
      request.cancelRequest(requestId);
      assert.equal(firstConfig.signal?.aborted, true);
      assert.equal(secondConfig.signal?.aborted, false);
      request.cancelRequest('unknown-request');
      assert.equal(secondConfig.signal?.aborted, false);
      request.cancelAllRequest();
      assert.equal(secondConfig.signal?.aborted, true);
    } finally {
      first.stop();
      second.stop();
      await Promise.all(results);
    }
  });
}

test('cancelAllRequest preserves caller-owned cancellation signals', async () => {
  const request = createRequest();
  const external = new AbortController();
  const pending = pendingAdapter();
  const result = assert.rejects(request({ url: '/external', adapter: pending.adapter, signal: external.signal }), {
    code: 'ERR_CANCELED'
  });
  await pending.started;
  try {
    request.cancelAllRequest();
    assert.equal(external.signal.aborted, false);
    external.abort();
  } finally {
    pending.stop();
    await result;
  }
});
