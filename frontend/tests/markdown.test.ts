import assert from 'node:assert/strict';
import { test } from 'node:test';
import { renderMarkdown } from '../src/utils/markdown';

test('escapes raw HTML from model answers and user input', () => {
  const html = renderMarkdown('<script>alert(1)</script>\n<img src=x onerror="alert(1)">');
  assert.doesNotMatch(html, /<(?:script|img)\b/i);
  assert.match(html, /&lt;script&gt;/);
  assert.match(html, /&lt;img /);
});

test('rejects unsafe Markdown links, including encoded schemes', () => {
  for (const url of ['javascript:alert(1)', 'jav&#x61;script:alert(1)', 'vbscript:alert(1)', 'data:text/html;base64,PHNjcmlwdD4=']) {
    assert.doesNotMatch(renderMarkdown(`[source](${url})`), /<a\b/);
  }
});

test('rejects scriptable image URLs', () => {
  for (const url of ['javascript:alert(1)', 'data:image/svg+xml;base64,PHN2Zz4=']) {
    assert.doesNotMatch(renderMarkdown(`![symptom](${url})`), /<img\b/);
  }
});

test('preserves safe evidence links, formatting and line breaks', () => {
  const html = renderMarkdown('**水稻**\n[资料](https://example.org/evidence?a=1&b=2)');
  assert.match(html, /<strong>水稻<\/strong><br>/);
  assert.match(html, /href="https:\/\/example.org\/evidence\?a=1&amp;b=2"/);
});

test('keeps automatic links optional for diagnosis answers', () => {
  assert.match(renderMarkdown('https://example.org'), /<a\b/);
  assert.doesNotMatch(renderMarkdown('https://example.org', false), /<a\b/);
  assert.equal(renderMarkdown(), '');
});
