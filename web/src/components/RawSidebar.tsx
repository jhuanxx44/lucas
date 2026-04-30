import { useEffect, useState } from "react";
import { ChevronDown, ChevronRight, FileText, FolderOpen, Building2, Factory, Plus } from "lucide-react";
import { fetchRawTree } from "@/lib/api";
import { useWikiNavigation } from "@/hooks/useWikiNavigation";
import { SourceUploadDialog } from "./SourceUploadDialog";
import type { RawTree, RawIndustry, RawCompany, RawReport } from "@/types";

function FileItem({ name, path }: { name: string; path: string }) {
  const { currentPath, navigateTo } = useWikiNavigation();
  const isPdf = name.endsWith(".pdf");
  const prefix = isPdf ? "__raw_pdf__/" : "__raw__/";
  const fullPath = `${prefix}${path}`;

  return (
    <button
      onClick={() => navigateTo(fullPath)}
      className={`flex items-center gap-2 text-sm w-full text-left px-2 py-1 rounded transition-colors ${
        currentPath === fullPath
          ? "bg-indigo-100 text-indigo-700 dark:bg-indigo-500/20 dark:text-indigo-300"
          : "text-zinc-600 hover:text-zinc-900 hover:bg-zinc-100 dark:text-zinc-400 dark:hover:text-zinc-200 dark:hover:bg-zinc-800"
      }`}
    >
      <FileText size={13} className="shrink-0" />
      <span className="truncate">{name}</span>
    </button>
  );
}

function ReportItem({ report }: { report: RawReport }) {
  const [open, setOpen] = useState(false);
  const displayFiles = report.files.filter((f) => f !== "meta.json");

  return (
    <div className="ml-2">
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-1.5 text-sm text-zinc-600 dark:text-zinc-400 hover:text-zinc-900 dark:hover:text-zinc-200 w-full py-0.5"
      >
        {open ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
        <span className="truncate">{report.name}</span>
      </button>
      {open && (
        <div className="ml-4 space-y-0.5">
          {displayFiles.map((f) => (
            <FileItem key={f} name={f} path={`${report.dir}/${f}`} />
          ))}
        </div>
      )}
    </div>
  );
}
function CompanyItem({ company }: { company: RawCompany }) {
  const [open, setOpen] = useState(false);

  return (
    <div className="ml-2">
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-1.5 text-sm text-zinc-700 dark:text-zinc-300 hover:text-zinc-900 dark:hover:text-zinc-100 w-full py-0.5 font-medium"
      >
        {open ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
        <Building2 size={13} className="shrink-0 text-zinc-400 dark:text-zinc-500" />
        <span className="truncate">{company.name}</span>
      </button>
      {open && (
        <div className="ml-4 space-y-0.5">
          {company.reports.map((r) => (
            <ReportItem key={r.dir} report={r} />
          ))}
        </div>
      )}
    </div>
  );
}

function IndustryItem({ industry }: { industry: RawIndustry }) {
  const [open, setOpen] = useState(false);

  return (
    <div>
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-1.5 text-sm text-zinc-800 dark:text-zinc-200 hover:text-zinc-900 dark:hover:text-zinc-100 w-full py-1 font-semibold"
      >
        {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        <Factory size={14} className="shrink-0 text-zinc-500 dark:text-zinc-400" />
        <span className="truncate">{industry.name}</span>
      </button>
      {open && (
        <div className="ml-2 space-y-0.5">
          {industry.companies.map((c) => (
            <CompanyItem key={c.name} company={c} />
          ))}
          {industry.reports.map((r) => (
            <ReportItem key={r.dir} report={r} />
          ))}
        </div>
      )}
    </div>
  );
}

export function RawSidebar() {
  const [tree, setTree] = useState<RawTree | null>(null);
  const [loading, setLoading] = useState(true);
  const [sourcesOpen, setSourcesOpen] = useState(false);
  const [uploadOpen, setUploadOpen] = useState(false);

  const loadTree = () => {
    fetchRawTree()
      .then(setTree)
      .catch(() => setTree(null))
      .finally(() => setLoading(false));
  };

  useEffect(() => { loadTree(); }, []);

  if (loading) return <div className="text-xs text-zinc-400 dark:text-zinc-500 p-2">加载中...</div>;
  if (!tree) return <div className="text-xs text-red-500 p-2">加载失败</div>;

  return (
    <div className="space-y-1">
      <button
        onClick={() => setUploadOpen(true)}
        className="flex items-center gap-1.5 text-xs text-indigo-600 dark:text-indigo-400 hover:text-indigo-700 dark:hover:text-indigo-300 w-full py-1 px-1 rounded hover:bg-indigo-50 dark:hover:bg-indigo-500/10 transition-colors mb-1"
      >
        <Plus size={13} />
        <span>收录材料</span>
      </button>
      {tree.industries.map((ind) => (
        <IndustryItem key={ind.name} industry={ind} />
      ))}
      {tree.sources.length > 0 && (
        <div className="pt-2 border-t border-zinc-200 dark:border-zinc-800 mt-2">
          <button
            onClick={() => setSourcesOpen(!sourcesOpen)}
            className="flex items-center gap-1.5 text-sm text-zinc-800 dark:text-zinc-200 hover:text-zinc-900 dark:hover:text-zinc-100 w-full py-1 font-semibold"
          >
            {sourcesOpen ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
            <FolderOpen size={14} className="shrink-0 text-zinc-500 dark:text-zinc-400" />
            <span>外部资料</span>
          </button>
          {sourcesOpen && (
            <div className="ml-4 space-y-0.5">
              {tree.sources.map((s) => (
                <FileItem key={s.path} name={s.name} path={s.path} />
              ))}
            </div>
          )}
        </div>
      )}
      <SourceUploadDialog
        open={uploadOpen}
        onClose={() => setUploadOpen(false)}
        onDone={() => { setUploadOpen(false); loadTree(); }}
      />
    </div>
  );
}
