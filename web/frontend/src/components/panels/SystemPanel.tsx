import HudFrame from "../HudFrame";
import type { SystemStats } from "../../api";

function Bar({ label, pct, unit }: { label: string; pct: number; unit?: string }) {
  const danger = pct > 85;
  const color = danger ? "#ff3b5c" : "#38e1ff";
  return (
    <div>
      <div className="mb-1 flex items-baseline justify-between">
        <span className="label text-ink-dim">{label}</span>
        <span className="mono text-sm" style={{ color }}>
          {Math.round(pct)}
          {unit ?? "%"}
        </span>
      </div>
      <div className="h-1.5 w-full overflow-hidden rounded-sm bg-cyan/10">
        <div
          className="h-full rounded-sm transition-all duration-500"
          style={{
            width: `${Math.min(100, pct)}%`,
            background: color,
            boxShadow: `0 0 8px ${color}`,
          }}
        />
      </div>
    </div>
  );
}

export default function SystemPanel({ system, delay }: { system: SystemStats | null; delay?: number }) {
  return (
    <HudFrame label="System Diagnostics" delay={delay}>
      {!system ? (
        <p className="label text-ink-mute">reading…</p>
      ) : (
        <div className="flex flex-col gap-3">
          <Bar label="CPU Load" pct={system.cpu_pct} />
          <Bar label="Memory" pct={system.ram_pct} />
          {system.battery && (
            <Bar label={`Power ${system.battery.charging ? "⚡" : ""}`} pct={system.battery.pct} />
          )}
          <div className="mono flex justify-between border-t border-[var(--edge)] pt-2 text-[0.7rem] text-ink-dim">
            <span>
              RAM {system.ram_used_gb}/{system.ram_total_gb}GB
            </span>
            <span>UP {system.uptime_str ?? "—"}</span>
          </div>
        </div>
      )}
    </HudFrame>
  );
}
