export function processWikiLinks(content: string): string {
  return content.replace(/\[\[([^\]]+)\]\]/g, "[$1](#wiki:$1)");
}
