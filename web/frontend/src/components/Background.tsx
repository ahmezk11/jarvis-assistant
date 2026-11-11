/** Fixed decorative HUD backdrop: grid, vignette, scanlines, frame ticks. */
export default function Background() {
  return (
    <div className="pointer-events-none fixed inset-0 z-0 overflow-hidden">
      {/* deep radial glow from centre */}
      <div
        className="absolute inset-0"
        style={{
          background:
            "radial-gradient(120% 90% at 50% 8%, rgba(56,225,255,0.10), transparent 55%), radial-gradient(90% 90% at 50% 120%, rgba(43,125,148,0.10), transparent 60%)",
        }}
      />
      {/* fine grid */}
      <div
        className="absolute inset-0 opacity-[0.35]"
        style={{
          backgroundImage:
            "linear-gradient(var(--grid) 1px, transparent 1px), linear-gradient(90deg, var(--grid) 1px, transparent 1px)",
          backgroundSize: "44px 44px",
          maskImage: "radial-gradient(circle at 50% 40%, black, transparent 85%)",
        }}
      />
      {/* horizontal scanlines */}
      <div
        className="absolute inset-0 opacity-[0.06]"
        style={{
          backgroundImage:
            "repeating-linear-gradient(0deg, #38e1ff 0px, #38e1ff 1px, transparent 1px, transparent 4px)",
        }}
      />
      {/* vignette */}
      <div
        className="absolute inset-0"
        style={{
          boxShadow: "inset 0 0 240px 60px rgba(0,0,0,0.85)",
        }}
      />
      {/* corner frame ticks */}
      {[
        "top-3 left-3 border-l-2 border-t-2",
        "top-3 right-3 border-r-2 border-t-2",
        "bottom-3 left-3 border-l-2 border-b-2",
        "bottom-3 right-3 border-r-2 border-b-2",
      ].map((cls, i) => (
        <div
          key={i}
          className={`absolute h-6 w-6 border-cyan/40 ${cls}`}
        />
      ))}
    </div>
  );
}
