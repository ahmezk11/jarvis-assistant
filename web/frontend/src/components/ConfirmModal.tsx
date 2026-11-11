import { AnimatePresence, motion } from "framer-motion";
import type { Confirm } from "../api";

/** EDITH-framed approval gate for side-effect actions (send mail, calendar
 *  writes, etc). Mirrors the old desktop confirmation dialog. */
export default function ConfirmModal({
  confirm,
  onDecide,
}: {
  confirm: Confirm | null;
  onDecide: (id: string, approve: boolean) => void;
}) {
  return (
    <AnimatePresence>
      {confirm && (
        <motion.div
          className="fixed inset-0 z-50 grid place-items-center bg-black/70 backdrop-blur-sm"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
        >
          <motion.div
            initial={{ scale: 0.92, opacity: 0, y: 10 }}
            animate={{ scale: 1, opacity: 1, y: 0 }}
            exit={{ scale: 0.92, opacity: 0 }}
            transition={{ type: "spring", stiffness: 260, damping: 22 }}
            className="glass hud-corners box-glow w-[min(92vw,460px)] p-5"
          >
            <div className="mb-3 flex items-center gap-2">
              <span className="h-2 w-2 rounded-full bg-gold animate-blink" style={{ boxShadow: "0 0 8px #ffb020" }} />
              <span className="label text-gold">Authorisation Required</span>
            </div>
            <h3 className="display mb-2 text-lg text-cyan-bright glow-cyan">{confirm.title}</h3>
            <pre className="mono mb-5 max-h-52 overflow-auto whitespace-pre-wrap rounded border border-[var(--edge)] bg-black/30 p-3 text-[0.8rem] text-ink-dim">
              {confirm.detail}
            </pre>
            <div className="flex justify-end gap-3">
              <button
                onClick={() => onDecide(confirm.id, false)}
                className="label rounded border border-red/50 px-4 py-2 text-red transition hover:bg-red/10"
              >
                Abort
              </button>
              <button
                onClick={() => onDecide(confirm.id, true)}
                className="label rounded border border-cyan px-4 py-2 text-cyan transition hover:bg-cyan/10 hover:glow-cyan"
                style={{ boxShadow: "0 0 10px rgba(56,225,255,.4)" }}
              >
                Authorise
              </button>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
