import type { WikiIndex, WikiPage, SearchResult } from "@/types";

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
