import { motion } from "framer-motion";
import ArcReactorCore from "./ArcReactorCore";

/**
 * Boot gate. Browsers block speech synthesis and the microphone until the user
 * interacts with the page, so the HUD can't greet on a cold load. This overlay
 * captures that first gesture — clicking it unlocks audio and cues Jarvis to
 * speak the briefing, which doubles as a cinematic power-on sequence.
 */
export default function BootOverlay({ onActivate }: { onActivate: () => void }) {
  return (
    <motion.div
      onClick={onActivate}
      initial={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.6 }}
      className="fixed inset-0 z-[60] grid cursor-pointer place-items-center bg-void"
      style={{ background: "radial-gradient(circle at 50% 45%, #061019, #04070e 70%)" }}
    >
      <div className="flex flex-col items-center gap-10">
        <ArcReactorCore size={220} state="idle" />
        <div className="text-center">
          <h1 className="display glow-cyan text-4xl font-black tracking-[0.4em] text-cyan-bright">
            E.D.I.T.H
          </h1>
          <p className="label mt-3 text-ink-dim">System on standby</p>
        </div>
        <motion.div
          animate={{ opacity: [0.4, 1, 0.4] }}
          transition={{ duration: 1.8, repeat: Infinity, ease: "easeInOut" }}
          className="flex flex-col items-center gap-2"
        >
          <div
            className="label rounded border border-cyan px-6 py-2.5 text-cyan"
            style={{ boxShadow: "0 0 16px rgba(56,225,255,.45)" }}
          >
            ◉ Initialise System ◉
          </div>
          <p className="mono text-[0.7rem] text-ink-mute">
            click anywhere to activate the voice interface
          </p>
        </motion.div>
      </div>
    </motion.div>
  );
}
