"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { getFacets, listBreaks, type BreakPage, type Facets, type ListQuery } from "@/lib/api";

const PAGE_SIZE = 25;

const FILTERS = [
  { key: "counterparty_id", label: "Counterparty" },
  { key: "break_type", label: "Break type" },
  { key: "status", label: "Status" },
  { key: "level", label: "Level" },
] as const;

function BreaksView() {
  const router = useRouter();
  const search = useSearchParams();
  const [facets, setFacets] = useState<Facets | null>(null);
  // The result is tagged with the query it answers, so a stale one reads as loading.
  const [result, setResult] = useState<{
    key: string;
    page?: BreakPage;
    error?: string;
  } | null>(null);

  const filters = Object.fromEntries(
    FILTERS.map(({ key }) => [key, search.get(key) ?? ""]),
  ) as Record<(typeof FILTERS)[number]["key"], string>;
  const offset = Math.max(0, Number(search.get("offset")) || 0);
  const queryKey = search.toString();
  const settled = result?.key === queryKey ? result : null;
  const page = settled?.page ?? null;
  const error = settled?.error ?? null;

  useEffect(() => {
    getFacets()
      .then(setFacets)
      .catch(() => setFacets(null));
  }, []);

  useEffect(() => {
    let current = true;
    listBreaks({ ...(filters as ListQuery), limit: PAGE_SIZE, offset })
      .then((page) => current && setResult({ key: queryKey, page }))
      .catch((e: Error) => current && setResult({ key: queryKey, error: e.message }));
    return () => {
      current = false;
    };
    // queryKey covers every filter and the offset.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [queryKey]);

  function update(changes: Record<string, string>) {
    const next = new URLSearchParams(search.toString());
    for (const [key, value] of Object.entries(changes)) {
      if (value) next.set(key, value);
      else next.delete(key);
    }
    router.replace(`/breaks${next.size ? `?${next}` : ""}`);
  }

  function options(key: (typeof FILTERS)[number]["key"]): string[] {
    const values = facets?.[key] ?? [];
    // "none" lets the reviewer find breaks that no level has explained yet.
    return key === "level" ? ["none", ...values] : values;
  }

  return (
    <main className="mx-auto w-full max-w-6xl space-y-4 p-6">
      <h1 className="text-2xl font-semibold tracking-tight">Breaks</h1>
      <div className="flex flex-wrap gap-3">
        {FILTERS.map(({ key, label }) => (
          <label key={key} className="flex flex-col gap-1 text-xs text-muted-foreground">
            {label}
            <select
              className="rounded-md border bg-background px-2 py-1 text-sm text-foreground"
              value={filters[key]}
              onChange={(e) => update({ [key]: e.target.value, offset: "" })}
            >
              <option value="">All</option>
              {options(key).map((value) => (
                <option key={value} value={value}>
                  {value}
                </option>
              ))}
            </select>
          </label>
        ))}
      </div>

      {error && (
        <p role="alert" className="text-sm text-destructive">
          Could not load breaks: {error}. Is the API running?
        </p>
      )}
      {!error && !page && <p className="text-sm text-muted-foreground">Loading...</p>}
      {page && page.items.length === 0 && (
        <p className="text-sm text-muted-foreground">No breaks match these filters.</p>
      )}
      {page && page.items.length > 0 && (
        <>
          <table className="w-full text-left text-sm">
            <thead className="border-b text-xs text-muted-foreground">
              <tr>
                <th className="py-2 pr-3">Record</th>
                <th className="pr-3">Counterparty</th>
                <th className="pr-3">Type</th>
                <th className="pr-3">Field</th>
                <th className="pr-3">Delta</th>
                <th className="pr-3">Status</th>
                <th className="pr-3">Explained by</th>
                <th>Cause</th>
              </tr>
            </thead>
            <tbody>
              {page.items.map((item) => (
                <tr key={item.id} className="border-b hover:bg-muted/50">
                  <td className="py-2 pr-3">
                    <Link className="underline" href={`/breaks/${item.id}`}>
                      {item.record_id}
                    </Link>
                  </td>
                  <td className="pr-3">{item.counterparty_id}</td>
                  <td className="pr-3">{item.break_type}</td>
                  <td className="pr-3">{item.field ?? "-"}</td>
                  <td className="pr-3 font-mono">{item.delta ?? "-"}</td>
                  <td className="pr-3">{item.status}</td>
                  <td className="pr-3">
                    {item.level ? `${item.level}: ${item.rule}` : "-"}
                  </td>
                  <td>{item.cause ?? "-"}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="flex items-center gap-3 text-sm">
            <Button
              variant="outline"
              disabled={offset === 0}
              onClick={() => update({ offset: String(Math.max(0, offset - PAGE_SIZE) || "") })}
            >
              Previous
            </Button>
            <span className="text-muted-foreground">
              {offset + 1}-{offset + page.items.length} of {page.total}
            </span>
            <Button
              variant="outline"
              disabled={offset + PAGE_SIZE >= page.total}
              onClick={() => update({ offset: String(offset + PAGE_SIZE) })}
            >
              Next
            </Button>
          </div>
        </>
      )}
    </main>
  );
}

export default function BreaksPage() {
  return (
    <Suspense fallback={<p className="p-6 text-sm text-muted-foreground">Loading...</p>}>
      <BreaksView />
    </Suspense>
  );
}
