const ID_MAP = { "7. refunds and cancellation": "refunds" };

const SAFE_URL = /^(https?:|mailto:|\/)/i;

const href = (url) => (SAFE_URL.test(url.trim()) ? url.trim() : "#");

const inline = (text) =>
  text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/\*\*(.+?)\*\*/g, '<strong class="text-white">$1</strong>')
    .replace(
      /\[(.+?)\]\((.+?)\)/g,
      (_m, label, url) =>
        `<a href="${href(url)}" class="text-[#00ffcc] underline decoration-dotted">${label}</a>`
    )
    .replace(
      /(^|[\s(])((?:https?:\/\/|www\.)[^\s)]+)/g,
      '$1<a href="$2" class="text-[#00ffcc] underline decoration-dotted">$2</a>'
    )
    .replace(
      /([\w.+-]+@[\w-]+\.[\w.]+)/g,
      '<a href="mailto:$1" class="text-[#00ffcc] underline decoration-dotted">$1</a>'
    );

// Just enough markdown for the legal documents: headings, bullets and paragraphs.
export const Markdown = ({ text }) => {
  const blocks = [];
  let list = [];

  const flush = () => {
    if (list.length) {
      blocks.push(
        <ul key={`ul-${blocks.length}`} className="mt-4 space-y-2.5 pl-5">
          {list.map((item, n) => (
            <li
              key={n}
              className="list-disc text-sm leading-relaxed text-zinc-400 marker:text-[#00ffcc]"
              dangerouslySetInnerHTML={{ __html: inline(item) }}
            />
          ))}
        </ul>
      );
      list = [];
    }
  };

  (text || "").split("\n").forEach((raw, n) => {
    const line = raw.trim();
    if (!line) {
      flush();
      return;
    }
    if (line.startsWith("- ")) {
      list.push(line.slice(2));
      return;
    }
    flush();
    if (line.startsWith("### ")) {
      blocks.push(
        <h3
          key={n}
          className="mt-8 text-[11px] uppercase tracking-[0.25em] text-[#00ffcc]"
          dangerouslySetInnerHTML={{ __html: inline(line.slice(4)) }}
        />
      );
    } else if (line.startsWith("## ")) {
      const heading = line.slice(3);
      blocks.push(
        <h2
          key={n}
          id={ID_MAP[heading.toLowerCase()]}
          className="mt-12 scroll-mt-24 font-display text-lg tracking-tight text-white md:text-lg"
          dangerouslySetInnerHTML={{ __html: inline(heading) }}
        />
      );
    } else if (line.startsWith("# ")) {
      blocks.push(
        <p key={n} className="text-[10px] uppercase tracking-[0.3em] text-zinc-600">
          {line.slice(2)}
        </p>
      );
    } else {
      blocks.push(
        <p
          key={n}
          className="mt-4 text-sm leading-relaxed text-zinc-400"
          dangerouslySetInnerHTML={{ __html: inline(line) }}
        />
      );
    }
  });
  flush();

  return <div>{blocks}</div>;
};
