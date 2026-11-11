import { useEffect, useRef } from "react";

// Background "Hey Edith" wake-word listener built on the browser Speech
// Recognition API. Runs continuously while `active`, survives Chrome's habit of
// auto-stopping on silence (restarts on `onend`), and supports two phrasings:
//   • one-shot   — "hey edith, what's the weather"  → command sent immediately
//   • call-first — "hey edith" … then the next phrase is taken as the command
// It never uses the mic while paused (speaking / thinking / manual mic), so
// EDITH doesn't hear her own voice.

type SR = {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  start(): void;
  stop(): void;
  onresult: ((e: SpeechResultEvent) => void) | null;
  onerror: ((e: { error: string }) => void) | null;
  onend: (() => void) | null;
};
type SpeechResultEvent = {
  resultIndex: number;
  results: { length: number; [i: number]: { isFinal: boolean; 0: { transcript: string } } };
};

// "edith" plus common speech-recognition mishearings of it.
const WAKE = /\b(?:hey |ok |okay )?(?:edith|edit|eadith|e\.?d\.?i\.?t\.?h\.?)\b/i;

export function useWakeWord({
  active,
  onWakeHeard,
  onCommand,
  onCapturing,
  onDenied,
}: {
  active: boolean;
  onWakeHeard: () => void;
  onCommand: (text: string) => void;
  onCapturing: (on: boolean) => void;
  onDenied: () => void;
}) {
  const cbs = useRef({ onWakeHeard, onCommand, onCapturing, onDenied });
  cbs.current = { onWakeHeard, onCommand, onCapturing, onDenied };
  const activeRef = useRef(active);
  activeRef.current = active;

  const recRef = useRef<SR | null>(null);
  const awaitingRef = useRef(false);
  const deniedRef = useRef(false);
  const awaitTimer = useRef<number | null>(null);
  const restartTimer = useRef<number | null>(null);

  useEffect(() => {
    const Ctor =
      (window as unknown as { SpeechRecognition?: new () => SR; webkitSpeechRecognition?: new () => SR })
        .SpeechRecognition ||
      (window as unknown as { webkitSpeechRecognition?: new () => SR }).webkitSpeechRecognition;
    if (!Ctor) return;

    const clearAwait = () => {
      if (awaitingRef.current) {
        awaitingRef.current = false;
        cbs.current.onCapturing(false);
      }
      if (awaitTimer.current) {
        clearTimeout(awaitTimer.current);
        awaitTimer.current = null;
      }
    };

    const handleFinal = (raw: string) => {
      const t = raw.trim();
      if (!t) return;
      // Already greeted — this phrase is the command.
      if (awaitingRef.current) {
        clearAwait();
        cbs.current.onCommand(t);
        return;
      }
      const m = WAKE.exec(t);
      if (!m) return;
      cbs.current.onWakeHeard();
      const after = t.slice(m.index + m[0].length).replace(/^[\s,.:;!?-]+/, "").trim();
      if (after) {
        cbs.current.onCommand(after);
      } else {
        awaitingRef.current = true;
        cbs.current.onCapturing(true);
        awaitTimer.current = window.setTimeout(clearAwait, 9000);
      }
    };

    const start = () => {
      if (recRef.current || deniedRef.current) return;
      const rec = new Ctor();
      rec.lang = "en-US";
      rec.continuous = true;
      rec.interimResults = true;
      rec.onresult = (e) => {
        for (let i = e.resultIndex; i < e.results.length; i++) {
          if (e.results[i].isFinal) handleFinal(e.results[i][0].transcript);
        }
      };
      rec.onerror = (e) => {
        if (e.error === "not-allowed" || e.error === "service-not-allowed") {
          deniedRef.current = true;
          cbs.current.onDenied();
        }
      };
      rec.onend = () => {
        recRef.current = null;
        if (activeRef.current && !deniedRef.current) {
          restartTimer.current = window.setTimeout(() => {
            if (activeRef.current) start();
          }, 400);
        }
      };
      recRef.current = rec;
      try {
        rec.start();
      } catch {
        /* start() throws if already running — ignore */
      }
    };

    const stop = () => {
      if (restartTimer.current) {
        clearTimeout(restartTimer.current);
        restartTimer.current = null;
      }
      const rec = recRef.current;
      recRef.current = null;
      if (rec) {
        rec.onend = null; // don't auto-restart a deliberate stop
        try {
          rec.stop();
        } catch {
          /* ignore */
        }
      }
      // NB: a transient pause keeps `awaitingRef` so a mid-greeting pause
      // (e.g. the ack chime) doesn't lose the pending command.
    };

    if (active) start();
    else stop();
    return stop;
  }, [active]);
}
