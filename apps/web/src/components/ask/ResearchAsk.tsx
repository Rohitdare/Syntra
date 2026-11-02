"use client";

import React, { FormEvent, useState } from "react";
import { askProjectStream, getBrief, streamJobEvents } from "@/lib/api/client";
import { BriefResponse, BriefSummary, StreamEvent } from "@/lib/api/schemas";
import { BriefResponseSchema } from "@/lib/api/schemas";
import { ApiClientError } from "@/lib/api/client";
import { BookOpenIcon, SparklesIcon } from "@/components/ui/Icons";

interface ResearchAskProps {
  projectId: string;
  briefs: BriefSummary[];
  onOpenSource: (sourceId: string) => void;
  onBriefSaved: () => void;
}

export function ResearchAsk({
  projectId,
  briefs,
  onOpenSource,
  onBriefSaved,
}: ResearchAskProps) {
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<BriefResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [trace, setTrace] = useState<StreamEvent[]>([]);
  const [loadingBriefId, setLoadingBriefId] = useState<string | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    await runQuestion(question.trim());
  }

  async function runQuestion(value: string) {
    if (busy || value.length < 5 || value.length > 500) return;
    setQuestion(value);
    setAnswer(null);
    setError(null);
    setTrace([]);
    setBusy(true);

    let jobId: string | null = null;
    let lastSeq = 0;
    let reachedEnd = false;
    const events: StreamEvent[] = [];
    const handleEvent = (event: StreamEvent) => {
      if (event.type === "heartbeat") return;
      lastSeq = Math.max(lastSeq, event.seq);
      events.push(event);
      setTrace([...events]);
      if (event.type === "result" && event.data) {
        const parsed = BriefResponseSchema.safeParse(event.data);
        if (parsed.success) setAnswer(parsed.data);
        else setError("The saved brief response was incomplete. Open it from Previous briefs to retry loading.");
      } else if (event.type === "error") {
        setError(event.message || "The Writer could not complete this brief.");
      } else if (event.type === "stage_end") {
        reachedEnd = true;
        if (event.data?.status === "succeeded") onBriefSaved();
        else setError("The Writer could not complete this brief. You can retry the question.");
      }
    };

    let streamError: unknown;
    try {
      await askProjectStream({
        projectId,
        question: value,
        idempotencyKey: `ask_${crypto.randomUUID()}`,
        onJobId: (id) => { jobId = id; },
        onEvent: handleEvent,
      });
    } catch (err: unknown) {
      streamError = err;
    }

    if (!reachedEnd && jobId) {
      for (let attempt = 0; attempt < 3 && !reachedEnd; attempt += 1) {
        if (attempt > 0) await new Promise((resolve) => setTimeout(resolve, attempt * 1000));
        try {
          await streamJobEvents({ jobId, afterSeq: lastSeq, onEvent: handleEvent });
        } catch (err: unknown) {
          streamError = err;
        }
      }
    }

    if (!reachedEnd && !error) {
      setError(
        streamError instanceof ApiClientError
          ? `${streamError.message} The job may still be running; check Previous briefs again shortly.`
          : "The connection ended before the brief completed. Check Previous briefs or retry the question."
      );
    }
    setBusy(false);
  }

  async function openBrief(briefId: string) {
    setLoadingBriefId(briefId);
    setError(null);
    try {
      const saved = await getBrief(projectId, briefId);
      setAnswer(saved);
      setQuestion(saved.question);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Could not load this saved brief.");
    } finally {
      setLoadingBriefId(null);
    }
  }

  function renderCitedAnswer(text: string, legend: BriefResponse["legend"]) {
    const sourceByTag = new Map(legend.map((source) => [source.tag, source]));
    return text.split(/(\[S\d+\])/g).map((part, index) => {
      const tag = /^\[(S\d+)\]$/.exec(part)?.[1];
      const source = tag ? sourceByTag.get(tag) : undefined;
      if (!source) return <React.Fragment key={`${index}-${part}`}>{part}</React.Fragment>;
      return (
        <button
          key={`${index}-${tag}`}
          type="button"
          onClick={() => onOpenSource(source.sourceId)}
          title={`Open ${source.title}`}
          className="font-medium text-[var(--color-primary)] underline decoration-[var(--color-primary)]/40 underline-offset-2 hover:decoration-current"
        >
          [{tag}]
        </button>
      );
    });
  }

  return (
    <div className="mx-auto max-w-3xl space-y-5">
      <form
        onSubmit={submit}
        className="space-y-4 rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] p-5 sm:p-7"
      >
        <div className="flex items-start gap-3">
          <div className="rounded-xl bg-[var(--color-surface-secondary)] p-2 text-[var(--color-agent-writer)]">
            <BookOpenIcon className="h-5 w-5" />
          </div>
          <div>
            <h2 className="text-base font-semibold text-[var(--color-text-primary)]">Ask your evidence</h2>
            <p className="mt-1 text-xs leading-relaxed text-[var(--color-text-secondary)]">
              Get a concise answer grounded in your sources, with clickable citations, disagreements, and evidence gaps.
            </p>
          </div>
        </div>
        <textarea
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          minLength={5}
          maxLength={500}
          required
          rows={3}
          placeholder="What do the sources say about…?"
          className="w-full resize-y rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-secondary)] p-3 text-sm text-[var(--color-text-primary)] outline-none focus:border-[var(--color-primary)]"
        />
        {error && (
          <div role="alert" className="rounded-lg border border-[var(--color-error)]/30 bg-[var(--color-error-soft)] p-3 text-xs text-[var(--color-error)]">
            {error}
          </div>
        )}
        <div className="flex items-center justify-between">
          <span className="text-[11px] text-[var(--color-text-muted)]">{question.length}/500 · Evidence only</span>
          <button
            disabled={busy || question.trim().length < 5}
            className="inline-flex items-center gap-2 rounded-lg bg-[var(--color-primary)] px-4 py-2 text-xs font-medium text-white disabled:opacity-50"
          >
            <SparklesIcon className="h-3.5 w-3.5" />
            {busy ? "Writing brief…" : "Generate brief"}
          </button>
        </div>
      </form>

      {busy && (
        <div role="status" className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-4 text-xs text-[var(--color-text-secondary)]">
          {trace.at(-1)?.message || "Retrieving evidence…"}
        </div>
      )}

      {briefs.length > 0 && (
        <section className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] p-4 sm:p-5">
          <h3 className="text-xs font-semibold text-[var(--color-text-primary)]">Previous briefs</h3>
          <ul className="mt-2 divide-y divide-[var(--color-border-subtle)]">
            {briefs.map((brief) => (
              <li key={brief.id} className="flex items-center justify-between gap-3 py-2">
                <button
                  type="button"
                  disabled={loadingBriefId !== null}
                  onClick={() => void openBrief(brief.id)}
                  className="min-w-0 truncate text-left text-xs text-[var(--color-text-secondary)] hover:text-[var(--color-primary)] disabled:opacity-50"
                >
                  {brief.question}
                </button>
                <span className="shrink-0 text-[10px] text-[var(--color-text-muted)]">
                  {loadingBriefId === brief.id ? "Loading…" : new Date(brief.createdAt).toLocaleDateString()}
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {answer && (
        <article className="space-y-4 rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] p-5 sm:p-7">
          <div>
            <div className="text-[10px] font-semibold uppercase tracking-widest text-[var(--color-agent-writer)]">Research brief</div>
            <h3 className="mt-1 text-lg font-semibold text-[var(--color-text-primary)]">{answer.title}</h3>
            <p className="mt-1 text-[11px] text-[var(--color-text-muted)]">{answer.question}</p>
          </div>
          <div className="whitespace-pre-wrap text-sm leading-7 text-[var(--color-text-primary)]">
            {renderCitedAnswer(answer.answerMarkdown, answer.legend)}
          </div>
          {answer.legend.length > 0 && (
            <section className="rounded-xl border border-[var(--color-border-subtle)] bg-[var(--color-surface-secondary)]/50 p-3">
              <h4 className="text-[10px] font-semibold uppercase tracking-wider text-[var(--color-text-muted)]">Sources</h4>
              <ul className="mt-2 space-y-1">
                {answer.legend.map((source) => (
                  <li key={source.sourceId} className="text-[11px] text-[var(--color-text-secondary)]">
                    <button type="button" onClick={() => onOpenSource(source.sourceId)} className="mr-2 font-mono font-semibold text-[var(--color-primary)] hover:underline">[{source.tag}]</button>
                    {source.title}
                  </li>
                ))}
              </ul>
            </section>
          )}
          {answer.disagreements.length > 0 && (
            <section className="space-y-2">
              <h4 className="text-xs font-semibold text-[var(--color-text-primary)]">Source disagreements</h4>
              {answer.disagreements.map((item, index) => (
                <div key={`${item.topic}-${index}`} className="rounded-xl border border-[var(--color-agent-critic)]/20 bg-[var(--color-agent-critic)]/5 p-3 text-xs">
                  <div className="font-medium text-[var(--color-text-primary)]">{item.topic}</div>
                  {item.positions.map((position, positionIndex) => (
                    <p key={`${position.tag}-${positionIndex}`} className="mt-1 text-[var(--color-text-secondary)]">
                      <span className="font-mono">[{position.tag}]</span> {position.position}
                    </p>
                  ))}
                  {item.note && <p className="mt-2 text-[var(--color-text-muted)]">{item.note}</p>}
                </div>
              ))}
            </section>
          )}
          {answer.gaps && (
            <div className="rounded-xl bg-[var(--color-surface-secondary)] p-4 text-xs leading-relaxed text-[var(--color-text-secondary)]">
              <strong className="text-[var(--color-text-primary)]">Evidence gaps</strong>
              <p className="mt-1">{answer.gaps}</p>
            </div>
          )}
        </article>
      )}
    </div>
  );
}
