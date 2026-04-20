import { useCallback, useRef } from "react";

interface ResizableDividerProps {
  onResize: (delta: number) => void;
}

export function ResizableDivider({ onResize }: ResizableDividerProps) {
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

  return (
    <div
      className="w-1 bg-zinc-800 hover:bg-indigo-500 cursor-col-resize transition-colors shrink-0"
      onMouseDown={onMouseDown}
    />
  );
}
