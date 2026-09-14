/**
 * A generated review note, read safely.
 *
 * The content is model output. It is split on `### ` headings and every part
 * renders as React text — `**bold**` and `- ` lists are the only structure
 * recognised, exactly like the trade summary panel. There is no HTML path here
 * and there must never be one: no `dangerouslySetInnerHTML`, no Markdown
 * library, no parser that could turn a string into markup.
 *
 * The first section is always visible; the rest sit behind a native
 * "Read full note" disclosure, which is keyboard- and screen-reader-operable
 * with no script.
 */

function InlineMarkdown({ text }: { text: string }) {
  return text.split(/(\*\*[^*]+\*\*)/g).map((part, index) =>
    part.startsWith("**") && part.endsWith("**") ? (
      <strong key={index} className="font-semibold text-text">
        {part.slice(2, -2)}
      </strong>
    ) : (
      part
    ),
  );
}

function MarkdownBody({ body }: { body: string }) {
  return (
    <div className="mt-2 space-y-2 text-sm leading-6 text-muted">
      {body.split(/\n\s*\n/).map((block, index) => {
        const lines = block.split("\n").filter(Boolean);
        if (lines.length > 0 && lines.every((line) => /^[-*] /.test(line))) {
          return (
            <ul key={index} className="list-disc space-y-1 pl-5">
              {lines.map((line, lineIndex) => (
                <li key={`${lineIndex}:${line}`}>
                  <InlineMarkdown text={line.slice(2)} />
                </li>
              ))}
            </ul>
          );
        }
        return (
          <p key={index} className="whitespace-pre-line break-words">
            <InlineMarkdown text={block} />
          </p>
        );
      })}
    </div>
  );
}

export const SMALL_SAMPLE_LIMITATION = "Small sample — read this as a description, not a rule.";

/** How much a note's sample can carry: under five trades is low, under fifteen medium. */
export function sampleConfidence(reviewedTrades: number): "low" | "medium" | "high" {
  if (reviewedTrades < 5) return "low";
  if (reviewedTrades < 15) return "medium";
  return "high";
}

type Section = { title: string; body: string };

export function splitSections(content: string): Section[] {
  const [preamble = "", ...chunks] = content.split(/^### /m);
  const sections = chunks.map((chunk) => {
    const [title = "", ...body] = chunk.trim().split("\n");
    return { title: title.trim(), body: body.join("\n").trim() };
  });
  // Text before the first heading is kept, not dropped: a note that lost its
  // opening would read as a different note.
  return preamble.trim() ? [{ title: "", body: preamble.trim() }, ...sections] : sections;
}

function NoteSection({ section }: { section: Section }) {
  return (
    <section>
      {section.title && (
        <h3 className="font-display text-base font-bold text-text">{section.title}</h3>
      )}
      {section.body && <MarkdownBody body={section.body} />}
    </section>
  );
}

export function ReviewNote({
  title,
  sample,
  content,
  confidence,
  limitation,
}: {
  title: string;
  sample: string;
  content: string;
  confidence: string;
  limitation?: string;
}) {
  const [first, ...rest] = splitSections(content);

  return (
    <article className="mt-6 rounded-xl border border-line bg-surface p-5">
      <h2 className="font-display text-xl font-bold">{title}</h2>
      <p className="mt-1 font-mono text-[11px] uppercase tracking-[0.12em] text-muted">
        {sample} · Confidence: {confidence}
      </p>
      {limitation && <p className="mt-2 text-sm text-muted">{limitation}</p>}

      <div className="mt-5 space-y-5">
        {first && <NoteSection section={first} />}
        {rest.length > 0 && (
          <details className="group">
            <summary className="inline-flex min-h-11 cursor-pointer items-center text-sm font-medium text-accent hover:underline">
              Read full note
            </summary>
            <div className="mt-3 space-y-5">
              {rest.map((section, index) => (
                <NoteSection key={`${index}:${section.title}`} section={section} />
              ))}
            </div>
          </details>
        )}
      </div>
    </article>
  );
}
