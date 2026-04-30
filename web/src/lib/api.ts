import type { WikiIndex, WikiPage, SearchResult, RawTree, WikiTreeNode } from "@/types";
import { userHeaders } from "./userId";

const BASE = "/api";

export async function fetchWikiIndex(): Promise<WikiIndex> {
  const res = await fetch(`${BASE}/wiki/index`, { headers: userHeaders() });
  if (!res.ok) throw new Error(`Failed to fetch wiki index: ${res.status}`);
  return res.json();
}

export async function fetchWikiPage(path: string): Promise<WikiPage> {
  const safePath = path.split("/").map(encodeURIComponent).join("/");
  const res = await fetch(`${BASE}/wiki/${safePath}`, { headers: userHeaders() });
  if (!res.ok) throw new Error(`Failed to fetch wiki page: ${res.status}`);
  return res.json();
}

export async function searchWiki(query: string): Promise<SearchResult[]> {
  const res = await fetch(`${BASE}/wiki/search?q=${encodeURIComponent(query)}`, { headers: userHeaders() });
  if (!res.ok) throw new Error(`Search failed: ${res.status}`);
  return res.json();
}

export async function fetchRawTree(): Promise<RawTree> {
  const res = await fetch(`${BASE}/wiki/raw-tree`, { headers: userHeaders() });
  if (!res.ok) throw new Error(`Failed to fetch raw tree: ${res.status}`);
  return res.json();
}

export async function fetchRawFile(path: string): Promise<WikiPage> {
  const safePath = path.split("/").map(encodeURIComponent).join("/");
  const res = await fetch(`${BASE}/wiki/raw/${safePath}`, { headers: userHeaders() });
  if (!res.ok) throw new Error(`Failed to fetch raw file: ${res.status}`);
  return res.json();
}

export function rawPdfUrl(path: string): string {
  const safePath = path.split("/").map(encodeURIComponent).join("/");
  return `${BASE}/wiki/raw/${safePath}`;
}

export async function fetchRawReport(rawPath: string): Promise<WikiPage> {
  const stripped = rawPath.replace(/^raw\//, "");
  return fetchRawFile(stripped);
}

export async function fetchWikiTree(): Promise<WikiTreeNode[]> {
  const res = await fetch(`${BASE}/wiki/tree`, { headers: userHeaders() });
  if (!res.ok) throw new Error(`Failed to fetch wiki tree: ${res.status}`);
  return res.json();
}

export async function wikiMkdir(path: string): Promise<void> {
  const res = await fetch(`${BASE}/wiki/mkdir`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...userHeaders() },
    body: JSON.stringify({ path }),
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data.detail || `mkdir failed: ${res.status}`);
  }
}

export async function wikiMove(src: string, dst: string): Promise<void> {
  const res = await fetch(`${BASE}/wiki/move`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...userHeaders() },
    body: JSON.stringify({ src, dst }),
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data.detail || `move failed: ${res.status}`);
  }
}

export interface FetchSourceResult {
  content: string;
  url: string;
  content_type: string;
}

export async function fetchSource(url: string): Promise<FetchSourceResult> {
  const res = await fetch(`${BASE}/wiki/fetch-source`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...userHeaders() },
    body: JSON.stringify({ url }),
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data.detail || `抓取失败: ${res.status}`);
  }
  return res.json();
}

export interface ClassifyAlternative {
  industry: string;
  reason: string;
}

export interface ClassifyResult {
  title: string;
  industry: string;
  company: string;
  confidence: "high" | "low";
  alternatives: ClassifyAlternative[];
}

export async function classifySource(content: string): Promise<ClassifyResult> {
  const res = await fetch(`${BASE}/wiki/classify-source`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...userHeaders() },
    body: JSON.stringify({ content }),
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data.detail || `分类失败: ${res.status}`);
  }
  return res.json();
}

export interface IngestSourceParams {
  content: string;
  url?: string;
  title: string;
  industry: string;
  company?: string;
}

export interface IngestEvent {
  event: string;
  data: Record<string, unknown>;
}

export async function ingestSource(
  params: IngestSourceParams,
  onEvent: (evt: IngestEvent) => void,
): Promise<void> {
  const res = await fetch(`${BASE}/wiki/ingest-source`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...userHeaders() },
    body: JSON.stringify(params),
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data.detail || `收录失败: ${res.status}`);
  }
  const reader = res.body?.getReader();
  if (!reader) return;
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() || "";
    let currentEvent = "";
    for (const line of lines) {
      if (line.startsWith("event: ")) {
        currentEvent = line.slice(7);
      } else if (line.startsWith("data: ") && currentEvent) {
        try {
          const data = JSON.parse(line.slice(6));
          onEvent({ event: currentEvent, data });
        } catch { /* skip malformed */ }
        currentEvent = "";
      }
    }
  }
}
