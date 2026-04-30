import type { WikiIndex, WikiPage, SearchResult, RawTree, WikiTreeNode } from "@/types";

const BASE = "/api";

export async function fetchWikiIndex(): Promise<WikiIndex> {
  const res = await fetch(`${BASE}/wiki/index`);
  if (!res.ok) throw new Error(`Failed to fetch wiki index: ${res.status}`);
  return res.json();
}

export async function fetchWikiPage(path: string): Promise<WikiPage> {
  const safePath = path.split("/").map(encodeURIComponent).join("/");
  const res = await fetch(`${BASE}/wiki/${safePath}`);
  if (!res.ok) throw new Error(`Failed to fetch wiki page: ${res.status}`);
  return res.json();
}

export async function searchWiki(query: string): Promise<SearchResult[]> {
  const res = await fetch(`${BASE}/wiki/search?q=${encodeURIComponent(query)}`);
  if (!res.ok) throw new Error(`Search failed: ${res.status}`);
  return res.json();
}

export async function fetchRawTree(): Promise<RawTree> {
  const res = await fetch(`${BASE}/wiki/raw-tree`);
  if (!res.ok) throw new Error(`Failed to fetch raw tree: ${res.status}`);
  return res.json();
}

export async function fetchRawFile(path: string): Promise<WikiPage> {
  const safePath = path.split("/").map(encodeURIComponent).join("/");
  const res = await fetch(`${BASE}/wiki/raw/${safePath}`);
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
  const res = await fetch(`${BASE}/wiki/tree`);
  if (!res.ok) throw new Error(`Failed to fetch wiki tree: ${res.status}`);
  return res.json();
}

export async function wikiMkdir(path: string): Promise<void> {
  const res = await fetch(`${BASE}/wiki/mkdir`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
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
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ src, dst }),
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data.detail || `move failed: ${res.status}`);
  }
}
