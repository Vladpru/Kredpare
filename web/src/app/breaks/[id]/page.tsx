"use client";

import Link from "next/link";
import { use, useCallback, useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { decide, getBreak, type BreakDetail } from "@/lib/api";

type RecordData = NonNullable<BreakDetail["left_record"]>;

function isKey(name: string): boolean {
  return name === "id" || name.endsWith("_id");
}

/** Identifier fields first, then the compared field, then the rest, each group sorted. */
function fieldOrder(left: RecordData | null, right: RecordData | null, compared: string | null) {
  const names = new Set([...Object.keys(left?.data ?? {}), ...Object.keys(right?.data ?? {})]);
  const rank = (name: string) => (isKey(name) ? 0 : name === compared ? 1 : 2);
  return [...names].sort((a, b) => rank(a) - rank(b) || a.localeCompare(b));
}

function ComparisonTable({ detail }: { detail: BreakDetail }) {
  const { left_record: left, right_record: right, field } = detail;
  const cell = (record: RecordData | null, name: string) => record?.data[name] ?? "—";
  return (
    <section className="rounded-lg border p-4">
      <table className="w-full text-left text-sm">
        <thead className="border-b text-xs text-muted-foreground">
          <tr>
            <th className="py-1 pr-3 font-normal">Field</th>
            <th className="pr-3 font-normal">Left: {detail.left_schema}</th>
            <th className="font-normal">Right: {detail.right_schema ?? "—"}</th>
          </tr>
        </thead>
        <tbody>
          {fieldOrder(left, right, field).map((name) => (
            <tr
              key={name}
              className={name === field ? "bg-amber-100 font-semibold dark:bg-amber-900/40" : ""}
            >
              <td className="py-1 pr-3 text-muted-foreground">{name}</td>
              <td className="pr-3 font-mono">{cell(left, name)}</td>
              <td className="font-mono">{cell(right, name)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {!left && !right && (
        <p className="text-sm text-muted-foreground">No records stored for this break.</p>
      )}
      {(!left || !right) && (left || right) && (
        <p className="mt-2 text-sm text-muted-foreground">
          No record on the {left ? "right" : "left"} side.
        </p>
      )}
    </section>
  );
}

export default function BreakPage({ params }: PageProps<"/breaks/[id]">) {
  const { id } = use(params);
  const [detail, setDetail] = useState<BreakDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [comment, setComment] = useState("");
  const [reviewer, setReviewer] = useState("reviewer");
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const load = useCallback(() => {
    getBreak(id)
      .then(setDetail)
      .catch((e: Error) => setError(e.message));
  }, [id]);

  useEffect(load, [load]);

  async function submit(decision: "approve" | "reject") {
    setSubmitting(true);
    setSubmitError(null);
    try {
      await decide(id, { decision, comment }, reviewer.trim() || "reviewer");
      setComment("");
      load();
    } catch (e) {
      setSubmitError((e as Error).message);
    } finally {
      setSubmitting(false);
    }
  }

  const back = (
    <Link className="text-sm underline" href="/breaks">
      Back to breaks
    </Link>
  );

  if (error) {
    return (
      <main className="mx-auto w-full max-w-5xl space-y-3 p-6">
        {back}
        <p role="alert" className="text-sm text-destructive">
          Could not load this break: {error}
        </p>
      </main>
    );
  }
  if (!detail) {
    return (
      <main className="mx-auto w-full max-w-5xl p-6 text-sm text-muted-foreground">
        Loading...
      </main>
    );
  }

  const e = detail.explanation;
  return (
    <main className="mx-auto w-full max-w-5xl space-y-6 p-6">
      {back}
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">
          {detail.break_type} - {detail.record_id}
        </h1>
        <p className="text-sm text-muted-foreground">
          {detail.counterparty_id} / batch {detail.batch_id} / as of {detail.as_of} / status{" "}
          {detail.status}
        </p>
        {detail.field && (
          <p className="mt-1 text-sm">
            Field <span className="font-mono">{detail.field}</span>:{" "}
            <span className="font-mono">{detail.left_value ?? "-"}</span> vs{" "}
            <span className="font-mono">{detail.right_value ?? "-"}</span>
            {detail.delta && <> (delta <span className="font-mono">{detail.delta}</span>)</>}
          </p>
        )}
      </header>

      <ComparisonTable detail={detail} />

      <section className="rounded-lg border p-4">
        <h2 className="mb-2 text-sm font-medium">Explanation</h2>
        {e ? (
          <div className="space-y-2 text-sm">
            <p>
              Explained by <b>{e.level}</b>
              {e.level === "rule" ? <> (rule <span className="font-mono">{e.rule}</span>)</> : null}
            </p>
            <p>
              Cause: <b>{e.cause}</b>
            </p>
            <p>Wrong side: {e.wrong_side ?? "nobody yet"}</p>
            <p>Proposal: {e.proposal}</p>
            {e.citations.length > 0 && (
              <div>
                <p className="font-medium">Cited clauses</p>
                <ul className="list-disc space-y-1 pl-5">
                  {e.citations.map((c) => (
                    <li key={c.citation}>
                      <span className="font-mono">{c.citation}</span>
                      {c.text ? (
                        <blockquote className="border-l-2 pl-3 text-muted-foreground">
                          {c.text}
                        </blockquote>
                      ) : (
                        <span className="text-muted-foreground"> (clause text not available)</span>
                      )}
                    </li>
                  ))}
                </ul>
              </div>
            )}
            <details>
              <summary className="cursor-pointer text-muted-foreground">Evidence</summary>
              <pre className="mt-2 overflow-x-auto rounded bg-muted p-3 text-xs">
                {JSON.stringify(e.evidence, null, 2)}
              </pre>
            </details>
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">
            No explanation yet (status {detail.status}). This break needs a human.
          </p>
        )}
      </section>

      <section className="space-y-3 rounded-lg border p-4">
        <h2 className="text-sm font-medium">Decision</h2>
        <p className="text-xs text-muted-foreground">
          Recorded in the audit log only. Nothing is applied or sent.
        </p>
        <div className="flex flex-col gap-2 text-sm">
          <label className="flex flex-col gap-1">
            Reviewer
            <input
              className="rounded-md border bg-background px-2 py-1"
              value={reviewer}
              onChange={(ev) => setReviewer(ev.target.value)}
            />
          </label>
          <label className="flex flex-col gap-1">
            Comment
            <textarea
              className="rounded-md border bg-background px-2 py-1"
              rows={3}
              maxLength={2000}
              value={comment}
              onChange={(ev) => setComment(ev.target.value)}
            />
          </label>
        </div>
        <div className="flex gap-2">
          <Button disabled={submitting} onClick={() => submit("approve")}>
            Approve
          </Button>
          <Button variant="outline" disabled={submitting} onClick={() => submit("reject")}>
            Reject
          </Button>
        </div>
        {submitError && (
          <p role="alert" className="text-sm text-destructive">
            Decision not saved: {submitError}
          </p>
        )}
        <div>
          <h3 className="mb-1 text-sm font-medium">History</h3>
          {detail.decisions.length === 0 ? (
            <p className="text-sm text-muted-foreground">No decisions yet.</p>
          ) : (
            <ul className="space-y-1 text-sm">
              {detail.decisions.map((d) => (
                <li key={d.occurred_at + d.actor}>
                  <b>{d.decision}</b> by {d.actor} at {new Date(d.occurred_at).toLocaleString()}
                  {d.comment ? `: ${d.comment}` : ""}
                </li>
              ))}
            </ul>
          )}
        </div>
      </section>
    </main>
  );
}
