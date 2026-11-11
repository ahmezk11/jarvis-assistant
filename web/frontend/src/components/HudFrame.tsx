import { motion } from "framer-motion";
import type { ReactNode } from "react";

/** Standard glass HUD panel: labelled header with a status dot + travelling
 *  scan line, corner brackets, and a content area. */
export default function HudFrame({
  label,
  right,
  children,
  className = "",
  live = true,
  delay = 0,
}: {
  label: string;
  right?: ReactNode;
  children: ReactNode;
  className?: string;
  live?: boolean;
  delay?: number;
}) {
  return (
    <motion.section
      initial={{ opacity: 0, y: 14 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, delay, ease: "easeOut" }}
      className={`glass hud-corners flex min-h-0 flex-col ${className}`}
    >
      <header className="relative flex items-center justify-between border-b border-[var(--edge)] px-3 py-1.5">
        <div className="flex items-center gap-2">
          <span
            className={`h-1.5 w-1.5 rounded-full ${
              live ? "bg-cyan animate-blink" : "bg-ink-mute"
            }`}
            style={live ? { boxShadow: "0 0 8px #38e1ff" } : undefined}
          />
          <span className="label">{label}</span>
        </div>
        {right}
        <div className="scanline" style={{ top: "100%", ["--scan-h" as string]: "0px" }} />
      </header>
      <div className="min-h-0 flex-1 overflow-auto p-3">{children}</div>
    </motion.section>
  );
}
