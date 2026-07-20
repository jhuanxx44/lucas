import { useCallback, useRef } from "react";

interface ResizableDividerProps {
  label: string;
  onResize: (delta: number) => void;
}

export function ResizableDivider({ label, onResize }: ResizableDividerProps) {
  const startX = useRef(0);

  const onMouseDown = useCallback(
    (e: React.MouseEvent) => {
      startX.current = e.clientX;
      const onMouseMove = (ev: MouseEvent) => {
        const delta = ev.clientX - startX.current;
        startX.current = ev.clientX;
        onResize(delta);
      };
      const onMouseUp = () => {
        document.removeEventListener("mousemove", onMouseMove);
        document.removeEventListener("mouseup", onMouseUp);
        document.body.style.cursor = "";
        document.body.style.userSelect = "";
      };
      document.addEventListener("mousemove", onMouseMove);
      document.addEventListener("mouseup", onMouseUp);
      document.body.style.cursor = "col-resize";
      document.body.style.userSelect = "none";
    },
    [onResize]
  );

  const onKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === "ArrowLeft") onResize(-10);
      else if (e.key === "ArrowRight") onResize(10);
    },
    [onResize]
  );

  return (
    <div
      role="separator"
      aria-label={label}
      aria-orientation="vertical"
      tabIndex={0}
      className="group relative h-full w-2 shrink-0 cursor-col-resize outline-none"
      onMouseDown={onMouseDown}
      onKeyDown={onKeyDown}
    >
      <div className="absolute inset-y-0 left-1/2 w-px -translate-x-1/2 bg-zinc-200 transition-colors group-hover:bg-indigo-500 group-focus:bg-indigo-500 dark:bg-zinc-800" />
    </div>
  );
}
