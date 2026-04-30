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

export interface ChatAction {
  label: string;
  value: string;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  researchers?: ResearcherState[];
  synthesis?: string;
  actions?: ChatAction[];
}

export interface RawReport {
  name: string;
  dir: string;
  files: string[];
}

export interface RawCompany {
  name: string;
  reports: RawReport[];
}

export interface RawIndustry {
  name: string;
  companies: RawCompany[];
  reports: RawReport[];
}

export interface RawTree {
  industries: RawIndustry[];
  sources: { name: string; path: string }[];
}

export interface WikiTreeNode {
  name: string;
  path: string;
  type: "file" | "dir";
  children?: WikiTreeNode[];
}
