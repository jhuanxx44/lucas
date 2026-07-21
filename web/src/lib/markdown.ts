import type { PluggableList } from "unified";
import remarkGfm from "remark-gfm";

// 共享的 remark 配置：关闭 singleTilde，避免模型在数字区间里用单个 ~
// （如「约29~30亿」）被 GFM 误渲染成删除线；只有标准的 ~~ 才触发删除线。
export const REMARK_PLUGINS: PluggableList = [[remarkGfm, { singleTilde: false }]];

export function processWikiLinks(content: string): string {
  return content.replace(/\[\[([^\]]+)\]\]/g, "[$1](#wiki:$1)");
}
