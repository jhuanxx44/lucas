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

export interface ChatTraceStep {
  id: string;
  kind: "action" | "tool" | "thought" | "summary";
  label: string;
  status: "running" | "done" | "error";
  step?: number;
  tool?: string;
  input?: Record<string, unknown>;
  output?: string;
}

export interface ChatRuntimeTraceEvent {
  sequence: number;
  timestamp: string;
  event: string;
  step?: number;
  data: Record<string, unknown>;
}

export interface ChatRunConfig {
  agent: string;
  provider: string;
  model: string;
  temperature: number;
  allowed_tools: string[];
  max_steps: number;
  timeout_seconds: number;
  system_prompt: string;
  tools_description: string;
  prompt_template: string;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  researchers?: ResearcherState[];
  synthesis?: string;
  actions?: ChatAction[];
  processSteps?: string[];
  traceSteps?: ChatTraceStep[];
  runtimeTrace?: ChatRuntimeTraceEvent[];
  runConfig?: ChatRunConfig;
}

export interface ChatSessionSummary {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
  message_count: number;
}

export interface ChatSession extends Omit<ChatSessionSummary, "message_count"> {
  messages: ChatMessage[];
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
