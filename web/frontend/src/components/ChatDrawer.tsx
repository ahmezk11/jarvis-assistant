import { AnimatePresence, motion } from "framer-motion";
import ChatPanel from "./ChatPanel";
import type { Msg } from "../api";

/** The Comms Channel as a slide-out drawer, so the default view stays clean
 *  (reactor + widgets) and the chat opens on demand from a left-edge handle. */
export default function ChatDrawer({
  open,
  onToggle,
  messages,
  busy,
  onSend,
  onListening,
}: {
  open: boolean;
  onToggle: () => void;
  messages: Msg[];
  busy: boolean;
  onSend: (t: string) => void;
  onListening: (b: boolean) => void;
}) {
  return (
    <>
      {/* Edge handle — bright, glowing pull-tab so it's easy to spot */}
      {!open && (
        <button
          onClick={onToggle}
          title="Open comms channel"
          className="fixed left-0 top-1/2 z-40 flex -translate-y-1/2 items-center gap-2 rounded-r-md border border-l-0 border-cyan/70 bg-cyan/15 px-2.5 py-5 backdrop-blur transition hover:bg-cyan/25"
          style={{ writingMode: "vertical-rl", boxShadow: "0 0 18px rgba(56,225,255,.5)" }}
        >
          <span
            className={`h-2 w-2 rounded-full bg-cyan ${busy ? "animate-core" : "animate-blink"}`}
            style={{ boxShadow: "0 0 10px #38e1ff" }}
          />
          <span className="label rotate-180 text-sm tracking-[0.3em] text-cyan-bright glow-cyan">
            ⌨ COMMS
          </span>
        </button>
      )}

      <AnimatePresence>
        {open && (
          <>
            <motion.div
              className="fixed inset-0 z-40 bg-black/50 backdrop-blur-sm"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              onClick={onToggle}
            />
            <motion.aside
              className="glass hud-corners fixed inset-y-2 left-2 z-40 flex w-[min(92vw,440px)] flex-col p-3"
              initial={{ x: "-108%" }}
              animate={{ x: 0 }}
              exit={{ x: "-108%" }}
              transition={{ type: "spring", stiffness: 320, damping: 34 }}
            >
              <header className="mb-2 flex items-center justify-between border-b border-[var(--edge)] pb-2">
                <div className="flex items-center gap-2">
                  <span className="h-1.5 w-1.5 rounded-full bg-cyan animate-blink" style={{ boxShadow: "0 0 8px #38e1ff" }} />
                  <span className="label">Comms Channel</span>
                </div>
                <button onClick={onToggle} className="label text-ink-dim transition hover:text-cyan" title="Close">
                  ✕ Close
                </button>
              </header>
              <ChatPanel messages={messages} busy={busy} onSend={onSend} onListening={onListening} />
            </motion.aside>
          </>
        )}
      </AnimatePresence>
    </>
  );
}
