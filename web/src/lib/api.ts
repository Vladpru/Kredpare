import type { components, paths } from "@/lib/api-schema";

export type BreakPage = components["schemas"]["BreakPage"];
export type BreakSummary = components["schemas"]["BreakSummary"];
export type BreakDetail = components["schemas"]["BreakDetail"];
export type Facets = components["schemas"]["Facets"];
export type DecisionOut = components["schemas"]["DecisionOut"];
export type DecisionIn = components["schemas"]["DecisionIn"];
export type ListQuery = NonNullable<paths["/breaks"]["get"]["parameters"]["query"]>;

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, init);
  if (!response.ok) {
    throw new Error(
      response.status === 404 ? "Not found" : `Request failed (${response.status})`,
    );
  }
  return (await response.json()) as T;
}

export function listBreaks(query: ListQuery): Promise<BreakPage> {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value !== undefined && value !== null && value !== "") {
      params.set(key, String(value));
    }
  }
  return request<BreakPage>(`/breaks?${params}`);
}

export function getBreak(id: string): Promise<BreakDetail> {
  return request<BreakDetail>(`/breaks/${encodeURIComponent(id)}`);
}

export function decide(
  id: string,
  body: DecisionIn,
  reviewer: string,
): Promise<DecisionOut> {
  return request<DecisionOut>(`/breaks/${encodeURIComponent(id)}/decision`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Reviewer": reviewer },
    body: JSON.stringify(body),
  });
}

export function getFacets(): Promise<Facets> {
  return request<Facets>("/breaks/facets");
}
