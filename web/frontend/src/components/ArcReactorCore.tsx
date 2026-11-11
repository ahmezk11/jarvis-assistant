import { useMemo } from "react";

export type CoreState = "idle" | "thinking" | "listening" | "speaking";

const STATE_COLOR: Record<CoreState, string> = {
  idle: "#38e1ff",
  thinking: "#ffb020",
  listening: "#37f5a5",
  speaking: "#a6f2ff",
};

/**
 * The arc-reactor core: concentric rings of tick marks, dashes and segments
 * rotating at different speeds around a pulsing glass core — the Iron Man HUD signature.
 * `state` shifts the accent colour and animation energy.
 */
export default function ArcReactorCore({
  size = 340,
  state = "idle",
}: {
  size?: number;
  state?: CoreState;
}) {
  const color = STATE_COLOR[state];
  const c = size / 2;

  // Tick marks around the outer gauge ring.
  const ticks = useMemo(() => {
    const arr = [];
    const R = c - 6;
    for (let i = 0; i < 72; i++) {
      const a = (i / 72) * Math.PI * 2;
      const long = i % 6 === 0;
      const r1 = R - (long ? 12 : 6);
      arr.push({
        x1: c + Math.cos(a) * R,
        y1: c + Math.sin(a) * R,
        x2: c + Math.cos(a) * r1,
        y2: c + Math.sin(a) * r1,
        long,
      });
    }
    return arr;
  }, [c]);

  const energetic = state !== "idle";

  return (
    <div
      className="relative"
      style={{ width: size, height: size, filter: `drop-shadow(0 0 24px ${color}55)` }}
    >
      {/* Rotating gauge ring with tick marks */}
      <svg
        className="absolute inset-0 animate-spin-slow"
        width={size}
        height={size}
        viewBox={`0 0 ${size} ${size}`}
      >
        {ticks.map((t, i) => (
          <line
            key={i}
            x1={t.x1}
            y1={t.y1}
            x2={t.x2}
            y2={t.y2}
            stroke={color}
            strokeWidth={t.long ? 1.6 : 0.8}
            opacity={t.long ? 0.85 : 0.4}
          />
        ))}
        <circle
          cx={c}
          cy={c}
          r={c - 6}
          fill="none"
          stroke={color}
          strokeWidth="0.6"
          opacity="0.35"
        />
      </svg>

      {/* Counter-rotating dashed ring */}
      <svg
        className="absolute inset-0 animate-spin-slow-rev"
        width={size}
        height={size}
        viewBox={`0 0 ${size} ${size}`}
      >
        <circle
          cx={c}
          cy={c}
          r={c * 0.72}
          fill="none"
          stroke={color}
          strokeWidth="2"
          strokeDasharray="2 10"
          opacity="0.7"
        />
        <circle
          cx={c}
          cy={c}
          r={c * 0.62}
          fill="none"
          stroke={color}
          strokeWidth="6"
          strokeDasharray="40 26"
          opacity="0.18"
        />
      </svg>

      {/* Medium ring of segment blocks */}
      <svg
        className="absolute inset-0 animate-spin-med"
        width={size}
        height={size}
        viewBox={`0 0 ${size} ${size}`}
      >
        <circle
          cx={c}
          cy={c}
          r={c * 0.5}
          fill="none"
          stroke={color}
          strokeWidth="3"
          strokeDasharray="18 8"
          opacity="0.55"
          strokeLinecap="round"
        />
      </svg>

      {/* Glowing glass core */}
      <div className="absolute inset-0 grid place-items-center">
        <div
          className={energetic ? "animate-core" : "animate-core"}
          style={{
            width: size * 0.34,
            height: size * 0.34,
            borderRadius: "9999px",
            background: `radial-gradient(circle at 50% 42%, #ffffff, ${color} 34%, ${color}22 68%, transparent 74%)`,
            boxShadow: `0 0 26px ${color}, 0 0 70px ${color}aa, inset 0 0 22px ${color}`,
            animationDuration: state === "thinking" ? "0.7s" : state === "listening" ? "0.9s" : "1.5s",
          }}
        />
        {/* Inner triad reticle inside the core */}
        <svg
          className="absolute animate-spin-slow-rev"
          width={size * 0.34}
          height={size * 0.34}
          viewBox="0 0 100 100"
          style={{ opacity: 0.9 }}
        >
          <polygon
            points="50,14 84,72 16,72"
            fill="none"
            stroke="#04070e"
            strokeWidth="3"
            opacity="0.5"
          />
        </svg>
      </div>
    </div>
  );
}
