import HudFrame from "../HudFrame";
import type { AgentInfo } from "../../api";

const STATE_COLOR: Record<string, string> = {
  idle: "#2b7d94",
  queued: "#ffb020",
  running: "#37f5a5",
  done: "#38e1ff",
  error: "#ff3b5c",
};

/**
 * The specialist network as a constellation: EDITH at the core with her agents
 * on a ring around her, each node lighting up as it's queued / runs / reports.
 */
export default function AgentNetworkPanel({
  agents,
  activity,
  delay,
}: {
  agents: AgentInfo[];
  activity: Record<string, string>;
  delay?: number;
}) {
  const size = 190;
  const c = size / 2;
  const R = c - 30;
  const active = Object.values(activity).filter((s) => s === "running" || s === "queued").length;

  return (
    <HudFrame
      label="Agent Network"
      delay={delay}
      right={
        <span className="mono text-[0.62rem]" style={{ color: active ? "#37f5a5" : "#7398aa" }}>
          {active ? `${active} ACTIVE` : `${agents.length} READY`}
        </span>
      }
    >
      {agents.length === 0 ? (
        <p className="label text-ink-mute">no agents</p>
      ) : (
        <div className="flex flex-col items-center">
          <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
            {/* links from core to each specialist */}
            {agents.map((a, i) => {
              const ang = (i / agents.length) * Math.PI * 2 - Math.PI / 2;
              const x = c + Math.cos(ang) * R;
              const y = c + Math.sin(ang) * R;
              const st = activity[a.id] ?? "idle";
              const on = st === "running" || st === "queued";
              return (
                <line
                  key={`l-${a.id}`}
                  x1={c}
                  y1={c}
                  x2={x}
                  y2={y}
                  stroke={STATE_COLOR[st] ?? "#2b7d94"}
                  strokeWidth={on ? 1.4 : 0.6}
                  opacity={on ? 0.9 : 0.3}
                />
              );
            })}

            {/* core */}
            <circle cx={c} cy={c} r={13} fill="#04070e" stroke="#38e1ff" strokeWidth="1.5" />
            <circle cx={c} cy={c} r={5} fill="#a6f2ff" />
            <text
              x={c}
              y={c + 26}
              textAnchor="middle"
              fill="#7398aa"
              style={{ font: "600 6px Rajdhani, sans-serif", letterSpacing: "0.2em" }}
            >
              EDITH
            </text>

            {/* specialist nodes */}
            {agents.map((a, i) => {
              const ang = (i / agents.length) * Math.PI * 2 - Math.PI / 2;
              const x = c + Math.cos(ang) * R;
              const y = c + Math.sin(ang) * R;
              const st = activity[a.id] ?? "idle";
              const col = STATE_COLOR[st] ?? "#2b7d94";
              const on = st === "running" || st === "queued";
              return (
                <g key={a.id}>
                  <circle
                    cx={x}
                    cy={y}
                    r={on ? 7 : 5.5}
                    fill="#04070e"
                    stroke={col}
                    strokeWidth={on ? 2 : 1.2}
                    className={st === "running" ? "animate-core" : undefined}
                    style={on ? { filter: `drop-shadow(0 0 6px ${col})` } : undefined}
                  />
                  <text
                    x={x}
                    y={y + (Math.sin(ang) > 0.3 ? 17 : -11)}
                    textAnchor="middle"
                    fill={on ? col : "#7398aa"}
                    style={{ font: "600 6.5px Rajdhani, sans-serif", letterSpacing: "0.12em" }}
                  >
                    {a.label.toUpperCase()}
                  </text>
                </g>
              );
            })}
          </svg>

          <p className="mono mt-1 text-center text-[0.62rem] leading-snug text-ink-mute">
            {agents.reduce((n, a) => n + a.tool_count, 0)} tools across {agents.length} specialists
          </p>
        </div>
      )}
    </HudFrame>
  );
}
