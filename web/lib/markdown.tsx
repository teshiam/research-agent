import type { ReactNode } from "react";

// A deliberately small Markdown renderer that builds React elements (never raw HTML), so
// model-written text can't inject markup. Supports headings, lists, quotes, bold, links and [n] citations.

const INLINE = /(\*\*[^*]+\*\*|\[[^\]]+\]\(https?:\/\/[^)\s]+\)|\[\d+\])/g;

function inline(text: string, keyBase: string): ReactNode[] {
  return text.split(INLINE).map((part, i) => {
    const key = `${keyBase}-${i}`;
    if (part.startsWith("**") && part.endsWith("**") && part.length > 4) {
      return <strong key={key}>{part.slice(2, -2)}</strong>;
    }
    const link = part.match(/^\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)$/);
    if (link) {
      return (
        <a key={key} href={link[2]} target="_blank" rel="noopener noreferrer">
          {link[1]}
        </a>
      );
    }
    const cite = part.match(/^\[(\d+)\]$/);
    if (cite) {
      return (
        <a key={key} className="cite" href={`#src-${cite[1]}`}>
          {cite[1]}
        </a>
      );
    }
    return part;
  });
}

export function Markdown({ text }: { text: string }) {
  const lines = text.split("\n");
  const out: ReactNode[] = [];
  let inSources = false;
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];
    const key = `b${i}`;

    const heading = line.match(/^(#{1,3})\s+(.*)$/);
    if (heading) {
      const level = heading[1].length;
      inSources = heading[2].trim().toLowerCase() === "sources";
      const Tag = (`h${level}` as "h1" | "h2" | "h3");
      out.push(<Tag key={key}>{inline(heading[2], key)}</Tag>);
      i++;
      continue;
    }

    if (/^>\s?/.test(line)) {
      const quote: string[] = [];
      while (i < lines.length && /^>\s?/.test(lines[i])) quote.push(lines[i++].replace(/^>\s?/, ""));
      out.push(<blockquote key={key}>{inline(quote.join(" "), key)}</blockquote>);
      continue;
    }

    if (/^\s*[-*]\s+/.test(line)) {
      const items: string[] = [];
      while (i < lines.length && /^\s*[-*]\s+/.test(lines[i])) items.push(lines[i++].replace(/^\s*[-*]\s+/, ""));
      out.push(
        <ul key={key}>
          {items.map((item, n) => <li key={n}>{inline(item, `${key}-${n}`)}</li>)}
        </ul>,
      );
      continue;
    }

    if (/^\s*\d+\.\s+/.test(line)) {
      const items: { n: number; text: string }[] = [];
      while (i < lines.length && /^\s*\d+\.\s+/.test(lines[i])) {
        const m = lines[i++].match(/^\s*(\d+)\.\s+(.*)$/)!;
        items.push({ n: Number(m[1]), text: m[2] });
      }
      out.push(
        <ol key={key}>
          {items.map((item) => (
            <li key={item.n} id={inSources ? `src-${item.n}` : undefined} value={item.n}>
              {inline(item.text, `${key}-${item.n}`)}
            </li>
          ))}
        </ol>,
      );
      continue;
    }

    if (line.trim() === "") {
      i++;
      continue;
    }

    const paragraph: string[] = [];
    while (i < lines.length && lines[i].trim() !== "" && !/^(#{1,3}\s|>|\s*[-*]\s|\s*\d+\.\s)/.test(lines[i])) {
      paragraph.push(lines[i++]);
    }
    out.push(<p key={key}>{inline(paragraph.join(" "), key)}</p>);
  }

  return <div className="md">{out}</div>;
}
