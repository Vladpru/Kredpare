"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { listBreaks, type BreakPage, type ListQuery } from "@/lib/api";

const PAGE_SIZE = 25;

const FILTERS: { key: "counterparty_id" | "break_type" | "status" | "level"; label: string }[] = [
  { key: "counterparty_id", label: "Counterparty" },
  { key: "break_type", label: "Break type" },
  { key: "status", label: "Status" },
  { key: "level", label: "Level (or none)" },
];

export default function BreaksPage() {
  const [filters, setFilters] = useState<Record<string, string>>({});
  const [offset, setOffset] = useState(0);
  const [page, setPage] = useState<BreakPage | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let current = true;
    const timer = setTimeout(() => {
      setError(null);
      setPage(null);
      listBreaks({ ...(filters as ListQuery), limit: PAGE_SIZE, offset })
        .then((result) => current && setPage(result))
        .catch((e: Error) => current && setError(e.message));
    }, 250);
    return () => {
      current = false;
      clearTimeout(timer);
    };
  }, [filters, offset]);

  function setFilter(key: string, value: string) {
    setOffset(0);
    setFilters((previous) => ({ ...previous, [key]: value }));
  }

  return (
    <main className="mx-auto w-full max-w-6xl space-y-4 p-6">
      <h1 className="text-2xl font-semibold tracking-tight">Breaks</h1>
      <div className="flex flex-wrap gap-3">
        {FILTERS.map(({ key, label }) => (
          <label key={key} className="flex flex-col gap-1 text-xs text-muted-foreground">
            {label}
            <input
              className="rounded-md border bg-background px-2 py-1 text-sm text-foreground"
              value={filters[key] ?? ""}
              onChange={(e) => setFilter(key, e.target.value.trim())}
            />
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
              onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
            >
              Previous
            </Button>
            <span className="text-muted-foreground">
              {offset + 1}-{offset + page.items.length} of {page.total}
            </span>
            <Button
              variant="outline"
              disabled={offset + PAGE_SIZE >= page.total}
              onClick={() => setOffset(offset + PAGE_SIZE)}
            >
              Next
            </Button>
          </div>
        </>
      )}
    </main>
  );
}
