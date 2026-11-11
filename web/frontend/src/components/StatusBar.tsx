import { useClock } from "../hooks";
import type { Status, SystemStats } from "../api";

function Dot({ on, label }: { on: boolean; label: string }) {
  return (
    <div className="flex items-center gap-1.5" title={`${label}: ${on ? "online" : "offline"}`}>
      <span
        className={`h-2 w-2 rounded-full ${on ? "bg-green" : "bg-ink-mute"}`}
        style={on ? { boxShadow: "0 0 8px #37f5a5" } : undefined}
      />
      <span className="label text-[0.58rem]" style={{ color: on ? "#8fb6c6" : "#3f5c6a" }}>
        {label}
      </span>
    </div>
  );
}

export default function StatusBar({
  status,
  system,
  wake,
  onComms,
  brain,
}: {
  status: Status | null;
  system: SystemStats | null;
  wake: { active: boolean; capturing: boolean; onToggle: () => void };
  onComms: () => void;
  brain: { value: "claude" | "local"; onToggle: () => void };
}) {
  const isLocal = brain.value === "local";
  const { time, date } = useClock("Asia/Dubai");

  return (
    <header className="relative z-10 flex items-center justify-between border-b border-[var(--edge)] px-5 py-2.5">
      {/* Identity */}
      <div className="flex items-baseline gap-3">
        <h1 className="display glow-cyan text-2xl font-black tracking-[0.35em] text-cyan-bright">
          E.D.I.T.H
        </h1>
        <span className="label hidden text-ink-dim sm:inline">
          Even Dead, I'm The Hero
        </span>
      </div>

      {/* Clock */}
      <div className="absolute left-1/2 top-1/2 hidden -translate-x-1/2 -translate-y-1/2 flex-col items-center md:flex">
        <div className="mono glow-cyan text-2xl leading-none text-cyan-bright">{time}</div>
        <div className="label mt-1 text-[0.55rem] text-ink-dim">{date} · DUBAI</div>
      </div>

      {/* Integrations + host */}
      <div className="flex items-center gap-4">
        {/* Brain toggle — Claude (paid) vs local Ollama (free) */}
        <button
          onClick={brain.onToggle}
          title={
            isLocal
              ? "Brain: Local model (free). Click to switch to Claude (higher quality, uses credits)."
              : "Brain: Claude (best quality, uses credits). Click to switch to the free local model."
          }
          className="flex items-center gap-1.5 rounded border px-2 py-1 transition hover:bg-cyan/10"
          style={{
            borderColor: isLocal ? "rgba(55,245,165,.5)" : "rgba(56,225,255,.5)",
            boxShadow: isLocal ? "0 0 10px rgba(55,245,165,.3)" : "0 0 10px rgba(56,225,255,.3)",
          }}
        >
          <span style={{ color: isLocal ? "#37f5a5" : "#38e1ff" }}>◈</span>
          <span
            className="label text-[0.58rem]"
            style={{ color: isLocal ? "#8fe6c0" : "#a6f2ff" }}
          >
            {isLocal ? "Local · Free" : "Claude"}
          </span>
        </button>

        {/* Comms toggle */}
        <button
          onClick={onComms}
          title="Open comms channel (chat)"
          className="flex items-center gap-1.5 rounded border border-cyan/50 px-2 py-1 transition hover:bg-cyan/10"
          style={{ boxShadow: "0 0 10px rgba(56,225,255,.3)" }}
        >
          <span className="text-cyan">⌨</span>
          <span className="label text-[0.58rem] text-cyan-bright">Comms</span>
        </button>

        {/* Wake-word toggle */}
        <button
          onClick={wake.onToggle}
          title={wake.active ? "Wake word on — say 'Hey Edith'. Click to disable." : "Wake word off. Click to enable."}
          className="flex items-center gap-1.5 rounded border px-2 py-1 transition"
          style={{
            borderColor: wake.active ? "rgba(55,245,165,.5)" : "var(--edge)",
            boxShadow: wake.capturing ? "0 0 12px #37f5a5" : "none",
          }}
        >
          <span
            className={`h-2 w-2 rounded-full ${wake.active ? "bg-green" : "bg-ink-mute"} ${
              wake.capturing ? "animate-core" : wake.active ? "animate-blink" : ""
            }`}
            style={wake.active ? { boxShadow: "0 0 8px #37f5a5" } : undefined}
          />
          <span className="label text-[0.58rem]" style={{ color: wake.active ? "#8fe6c0" : "#3f5c6a" }}>
            {wake.capturing ? "Hearing…" : wake.active ? "Hey Edith" : "Wake Off"}
          </span>
        </button>

        <div className="hidden items-center gap-3 lg:flex">
          <Dot on={!!status?.claude} label="CLAUDE" />
          <Dot on={!!status?.google} label="GOOGLE" />
          <Dot on={!!status?.notion} label="NOTION" />
        </div>
        {system && (
          <div className="mono flex items-center gap-3 text-[0.7rem] text-ink-dim">
            <span>
              CPU <span className="text-cyan">{Math.round(system.cpu_pct)}%</span>
            </span>
            <span>
              MEM <span className="text-cyan">{Math.round(system.ram_pct)}%</span>
            </span>
            {system.battery && (
              <span>
                PWR <span className="text-cyan">{system.battery.pct}%</span>
                {system.battery.charging ? "⚡" : ""}
              </span>
            )}
          </div>
        )}
      </div>
    </header>
  );
}
