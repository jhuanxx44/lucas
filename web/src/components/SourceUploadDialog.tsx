import { useState } from "react";
import { X, Upload, Link, Loader2, ArrowRight, Check, RotateCcw } from "lucide-react";
import { fetchSource, classifySource, ingestSource } from "@/lib/api";
import type { ClassifyAlternative } from "@/lib/api";

interface Props {
  open: boolean;
  onClose: () => void;
  onDone: () => void;
}

type Step = "input" | "preview" | "classify" | "ingesting" | "done";
type InputTab = "text" | "url";

export function SourceUploadDialog({ open, onClose, onDone }: Props) {
  const [step, setStep] = useState<Step>("input");
  const [inputTab, setInputTab] = useState<InputTab>("text");
  const [url, setUrl] = useState("");
  const [content, setContent] = useState("");
  const [title, setTitle] = useState("");
  const [industry, setIndustry] = useState("");
  const [company, setCompany] = useState("");
  const [confidence, setConfidence] = useState<"high" | "low">("high");
  const [alternatives, setAlternatives] = useState<ClassifyAlternative[]>([]);
  const [loading, setLoading] = useState(false);
  const [status, setStatus] = useState<string[]>([]);
  const [error, setError] = useState("");

  if (!open) return null;

  const reset = () => {
    setStep("input");
    setInputTab("text");
    setUrl("");
    setContent("");
    setTitle("");
    setIndustry("");
    setCompany("");
    setConfidence("high");
    setAlternatives([]);
    setLoading(false);
    setStatus([]);
    setError("");
  };

  const handleClose = () => {
    if (step === "ingesting") return;
    reset();
    onClose();
  };

  // Step 1 → 2: fetch URL or go to preview
  const handleNext = async () => {
    setError("");
    if (inputTab === "url") {
      setLoading(true);
      try {
        const result = await fetchSource(url);
        setContent(result.content);
        setStep("preview");
      } catch (e) {
        setError(e instanceof Error ? e.message : "抓取失败");
      } finally {
        setLoading(false);
      }
    } else {
      setStep("preview");
    }
  };

  // Step 2 → 3: classify
  const handleClassify = async () => {
    setError("");
    setLoading(true);
    try {
      const result = await classifySource(content);
      setTitle(result.title);
      setIndustry(result.industry);
      setCompany(result.company);
      setConfidence(result.confidence);
      setAlternatives(result.alternatives || []);
      setStep("classify");
    } catch (e) {
      setError(e instanceof Error ? e.message : "分类失败");
    } finally {
      setLoading(false);
    }
  };

  // Step 3 → 4: ingest
  const handleIngest = async () => {
    setError("");
    setStep("ingesting");
    setStatus([]);
    let hasError = false;
    try {
      await ingestSource(
        { content, url: inputTab === "url" ? url : undefined, title, industry, company },
        (evt) => {
          if (evt.event === "status") setStatus((s) => [...s, evt.data.message as string]);
          else if (evt.event === "error") {
            setError(evt.data.message as string);
            hasError = true;
          }
        },
      );
      if (hasError) {
        setStep("classify");
      } else {
        setStep("done");
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "收录失败");
      setStep("classify");
    }
  };

  const canProceed = inputTab === "text" ? content.trim().length > 0 : url.trim().length > 0;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="bg-white dark:bg-zinc-900 rounded-xl shadow-xl w-full max-w-lg mx-4 overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-zinc-200 dark:border-zinc-800">
          <div className="flex items-center gap-3">
            <h3 className="text-sm font-semibold text-zinc-800 dark:text-zinc-200">收录材料</h3>
            <StepIndicator current={step} />
          </div>
          <button onClick={handleClose} className="text-zinc-400 hover:text-zinc-600 dark:hover:text-zinc-300">
            <X size={16} />
          </button>
        </div>

        {/* Body */}
        <div className="p-4 space-y-3">
          {step === "input" && (
            <>
              <div className="flex gap-1 bg-zinc-100 dark:bg-zinc-800 rounded-lg p-0.5">
                <TabBtn active={inputTab === "text"} onClick={() => setInputTab("text")} icon={<Upload size={12} />} label="粘贴文本" />
                <TabBtn active={inputTab === "url"} onClick={() => setInputTab("url")} icon={<Link size={12} />} label="输入 URL" />
              </div>
              {inputTab === "text" ? (
                <textarea
                  value={content}
                  onChange={(e) => setContent(e.target.value)}
                  placeholder="粘贴文章、研报或笔记内容..."
                  rows={8}
                  className="w-full bg-zinc-50 dark:bg-zinc-800 border border-zinc-200 dark:border-zinc-700 rounded-lg px-3 py-2 text-sm text-zinc-800 dark:text-zinc-200 placeholder:text-zinc-400 focus:outline-none focus:border-indigo-500 resize-none"
                />
              ) : (
                <input
                  value={url}
                  onChange={(e) => setUrl(e.target.value)}
                  placeholder="https://..."
                  className="w-full bg-zinc-50 dark:bg-zinc-800 border border-zinc-200 dark:border-zinc-700 rounded-lg px-3 py-2 text-sm text-zinc-800 dark:text-zinc-200 placeholder:text-zinc-400 focus:outline-none focus:border-indigo-500"
                />
              )}
            </>
          )}

          {step === "preview" && (
            <>
              <div className="text-xs text-zinc-500 dark:text-zinc-400 mb-1">
                预览内容（{content.length} 字）— 可编辑后再继续
              </div>
              <textarea
                value={content}
                onChange={(e) => setContent(e.target.value)}
                rows={10}
                className="w-full bg-zinc-50 dark:bg-zinc-800 border border-zinc-200 dark:border-zinc-700 rounded-lg px-3 py-2 text-xs text-zinc-800 dark:text-zinc-200 font-mono focus:outline-none focus:border-indigo-500 resize-none"
              />
            </>
          )}

          {step === "classify" && (
            <>
              <div className="text-xs text-zinc-500 dark:text-zinc-400 mb-1">
                {confidence === "low"
                  ? "分类不确定 — 请选择或修正行业归属"
                  : "自动分类结果 — 可修正后再收录"}
              </div>
              {confidence === "low" && alternatives.length > 0 && (
                <div className="flex flex-wrap gap-1.5 mb-2">
                  <button
                    onClick={() => {/* already selected */}}
                    className="px-2.5 py-1 text-xs rounded-lg bg-indigo-100 dark:bg-indigo-500/20 text-indigo-700 dark:text-indigo-300 border border-indigo-300 dark:border-indigo-500/40"
                  >
                    {industry}
                  </button>
                  {alternatives.map((alt) => (
                    <button
                      key={alt.industry}
                      onClick={() => setIndustry(alt.industry)}
                      className="px-2.5 py-1 text-xs rounded-lg border border-zinc-200 dark:border-zinc-700 text-zinc-600 dark:text-zinc-400 hover:border-indigo-300 dark:hover:border-indigo-500/40 hover:text-indigo-600 dark:hover:text-indigo-300 transition-colors"
                      title={alt.reason}
                    >
                      {alt.industry}
                    </button>
                  ))}
                </div>
              )}
              <div className="space-y-2">
                <LabeledInput label="标题" value={title} onChange={setTitle} />
                <LabeledInput label="行业" value={industry} onChange={setIndustry} />
                <LabeledInput label="公司" value={company} onChange={setCompany} placeholder="留空表示行业级材料" />
              </div>
            </>
          )}

          {step === "ingesting" && (
            <div className="space-y-1">
              <div className="flex items-center gap-2 text-xs text-zinc-500 dark:text-zinc-400">
                <Loader2 size={12} className="animate-spin" /> 正在收录并编译...
              </div>
              {status.map((msg, i) => (
                <div key={i} className="text-xs text-zinc-500 dark:text-zinc-400 pl-5">{msg}</div>
              ))}
            </div>
          )}

          {step === "done" && (
            <div className="flex flex-col items-center py-4 gap-2">
              <div className="w-8 h-8 rounded-full bg-green-100 dark:bg-green-500/15 flex items-center justify-center">
                <Check size={16} className="text-green-600 dark:text-green-400" />
              </div>
              <div className="text-sm text-zinc-700 dark:text-zinc-300">收录完成</div>
              {status.length > 0 && (
                <div className="text-xs text-zinc-400 dark:text-zinc-500 text-center">
                  {status[status.length - 1]}
                </div>
              )}
            </div>
          )}

          {error && (
            <div className="text-xs text-red-500 bg-red-50 dark:bg-red-500/10 rounded-lg p-2">{error}</div>
          )}
        </div>

        {/* Footer */}
        <div className="flex justify-between px-4 py-3 border-t border-zinc-200 dark:border-zinc-800">
          <div>
            {(step === "preview" || step === "classify") && (
              <button
                onClick={() => setStep(step === "preview" ? "input" : "preview")}
                className="flex items-center gap-1 px-3 py-1.5 text-xs text-zinc-500 dark:text-zinc-400 hover:text-zinc-700 dark:hover:text-zinc-200"
              >
                <RotateCcw size={11} /> 上一步
              </button>
            )}
          </div>
          <div className="flex gap-2">
            {step !== "ingesting" && (
              <button
                onClick={step === "done" ? () => { reset(); onDone(); } : handleClose}
                className="px-3 py-1.5 text-xs text-zinc-600 dark:text-zinc-400 hover:text-zinc-800 dark:hover:text-zinc-200"
              >
                {step === "done" ? "关闭" : "取消"}
              </button>
            )}
            {step === "input" && (
              <ActionBtn onClick={handleNext} disabled={!canProceed || loading} loading={loading}>
                {inputTab === "url" ? "抓取" : "下一步"} <ArrowRight size={12} />
              </ActionBtn>
            )}
            {step === "preview" && (
              <ActionBtn onClick={handleClassify} disabled={!content.trim() || loading} loading={loading}>
                自动分类 <ArrowRight size={12} />
              </ActionBtn>
            )}
            {step === "classify" && (
              <ActionBtn onClick={handleIngest} disabled={!title.trim() || !industry.trim()}>
                确认收录 <Check size={12} />
              </ActionBtn>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function StepIndicator({ current }: { current: Step }) {
  const steps: { key: Step; label: string }[] = [
    { key: "input", label: "输入" },
    { key: "preview", label: "预览" },
    { key: "classify", label: "分类" },
  ];
  const idx = steps.findIndex((s) => s.key === current);
  return (
    <div className="flex items-center gap-1">
      {steps.map((s, i) => (
        <span key={s.key} className={`text-[10px] px-1.5 py-0.5 rounded ${
          i <= idx ? "bg-indigo-100 text-indigo-700 dark:bg-indigo-500/20 dark:text-indigo-300" : "bg-zinc-100 text-zinc-400 dark:bg-zinc-800 dark:text-zinc-500"
        }`}>
          {s.label}
        </span>
      ))}
    </div>
  );
}

function TabBtn({ active, onClick, icon, label }: { active: boolean; onClick: () => void; icon: React.ReactNode; label: string }) {
  return (
    <button
      onClick={onClick}
      className={`flex-1 flex items-center justify-center gap-1.5 text-xs py-1.5 rounded-md transition-colors ${
        active ? "bg-white dark:bg-zinc-700 text-zinc-800 dark:text-zinc-200 shadow-sm" : "text-zinc-500 dark:text-zinc-400"
      }`}
    >
      {icon} {label}
    </button>
  );
}

function LabeledInput({ label, value, onChange, placeholder }: { label: string; value: string; onChange: (v: string) => void; placeholder?: string }) {
  return (
    <div className="flex items-center gap-2">
      <span className="text-xs text-zinc-500 dark:text-zinc-400 w-10 shrink-0">{label}</span>
      <input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="flex-1 bg-zinc-50 dark:bg-zinc-800 border border-zinc-200 dark:border-zinc-700 rounded-lg px-2 py-1.5 text-xs text-zinc-800 dark:text-zinc-200 placeholder:text-zinc-400 focus:outline-none focus:border-indigo-500"
      />
    </div>
  );
}

function ActionBtn({ onClick, disabled, loading, children }: { onClick: () => void; disabled?: boolean; loading?: boolean; children: React.ReactNode }) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className="flex items-center gap-1.5 px-3 py-1.5 text-xs bg-indigo-600 hover:bg-indigo-500 disabled:bg-zinc-300 dark:disabled:bg-zinc-700 text-white rounded-lg transition-colors"
    >
      {loading ? <Loader2 size={12} className="animate-spin" /> : children}
    </button>
  );
}
