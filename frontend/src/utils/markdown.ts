import MarkdownIt from 'markdown-it';

// Model answers and user input share the same HTML and URL safety defaults.
const markdown = new MarkdownIt({ html: false, linkify: true, breaks: true });
const markdownWithoutLinkify = new MarkdownIt({ html: false, breaks: true });

export function renderMarkdown(content = '', linkify = true): string {
  return (linkify ? markdown : markdownWithoutLinkify).render(content);
}
