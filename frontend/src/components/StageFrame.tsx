/**
 * The 1280x720 canvas, scaled to fit the window and letterboxed.
 *
 * This is what Ren'Py does with `gui.init(1280, 720)`, and copying it is what lets
 * every measurement in gui.rpy be used as the literal number it is — 185px of text
 * box, 268px of dialogue inset — instead of being re-derived as a percentage and
 * drifting from the Ren'Py build.
 */

import { useEffect, useRef, useState, type ReactNode } from "react";
import { STAGE_HEIGHT, STAGE_WIDTH } from "../config";

export function StageFrame({ children }: { children: ReactNode }) {
  const host = useRef<HTMLDivElement>(null);
  const [scale, setScale] = useState(1);

  useEffect(() => {
    const element = host.current;
    if (!element) return;
    const observer = new ResizeObserver(([entry]) => {
      const { width, height } = entry.contentRect;
      setScale(Math.min(width / STAGE_WIDTH, height / STAGE_HEIGHT));
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  return (
    <div ref={host} className="flex h-full w-full items-center justify-center bg-vn-void">
      <div
        className="relative overflow-hidden"
        style={{
          width: STAGE_WIDTH,
          height: STAGE_HEIGHT,
          transform: `scale(${scale})`,
          transformOrigin: "center",
        }}
      >
        {children}
      </div>
    </div>
  );
}
