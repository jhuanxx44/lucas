export interface WikiSection {
  title: string;
  items: WikiItem[];
}

export interface WikiItem {
  name: string;
  path: string;
  description?: string;
}

export interface WikiIndex {
  sections: WikiSection[];
}

export interface WikiPage {
  frontmatter: Record<string, unknown>;
  content: string;
  wiki_links: string[];
}

export interface SearchResult {
  name: string;
  path: string;
  snippet: string;
}

export type ResearcherStatus = "pending" | "running" | "done";

export interface ResearcherState {
  id: string;
  name: string;
  status: ResearcherStatus;
  text: string;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  researchers?: ResearcherState[];
  synthesis?: string;
}
