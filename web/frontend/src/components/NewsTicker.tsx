/** Bottom intel feed — headlines scrolling across the base of the HUD. */
export default function NewsTicker({ headlines }: { headlines: string[] }) {
  if (!headlines.length) return null;
  const line = headlines.join("     ◆     ");
  return (
    <div className="relative z-10 flex items-center gap-3 border-t border-[var(--edge)] bg-black/40 px-4 py-1.5">
      <span className="label shrink-0 text-gold glow-gold">Intel Feed</span>
      <div className="relative flex-1 overflow-hidden whitespace-nowrap">
        <div
          className="mono inline-block text-[0.78rem] text-ink-dim"
          style={{ animation: "ticker 60s linear infinite" }}
        >
          {line}
          <span className="mx-6 text-cyan-dim">◆</span>
          {line}
        </div>
      </div>
      <style>{`@keyframes ticker { from { transform: translateX(0) } to { transform: translateX(-50%) } }`}</style>
    </div>
  );
}
