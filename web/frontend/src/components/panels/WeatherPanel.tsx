import HudFrame from "../HudFrame";
import type { Weather } from "../../api";

export default function WeatherPanel({ weather, delay }: { weather: Weather | null; delay?: number }) {
  return (
    <HudFrame
      label="Environment"
      delay={delay}
      right={<span className="label text-ink-dim">{weather?.city ?? ""}</span>}
    >
      {!weather || !weather.available ? (
        <p className="label text-ink-mute">no signal</p>
      ) : (
        <div className="flex items-center justify-between">
          <div>
            <div className="display glow-cyan text-4xl font-bold leading-none text-cyan-bright">
              {weather.temp_c}°
            </div>
            <div className="mt-1 text-sm capitalize text-ink-dim">{weather.desc}</div>
          </div>
          <div className="mono space-y-1 text-right text-[0.7rem] text-ink-dim">
            <div>
              FEELS <span className="text-cyan">{weather.feels_c}°</span>
            </div>
            <div>
              HUM <span className="text-cyan">{weather.humidity}%</span>
            </div>
          </div>
        </div>
      )}
    </HudFrame>
  );
}
