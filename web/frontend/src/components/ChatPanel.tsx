import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import type { Msg } from "../api";

// Minimal typing for the browser SpeechRecognition API (not in TS DOM lib).
type SpeechRec = {
  lang: string;
  interimResults: boolean;
  continuous: boolean;
  start: () => void;
  stop: () => void;
  onresult: ((e: { results: { 0: { 0: { transcript: string } } } }) => void) | null;
  onerror: (() => void) | null;
  onend: (() => void) | null;
};

export default function ChatPanel({
  messages,
  busy,
  onSend,
  onListening,
}: {
  messages: Msg[];
  busy: boolean;
  onSend: (text: string) => void;
  onListening: (on: boolean) => void;
}) {
  const [text, setText] = useState("");
  const [listening, setListening] = useState(false);
  const recRef = useRef<SpeechRec | null>(null);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, busy]);

  const submit = (value?: string) => {
    const v = (value ?? text).trim();
    if (!v || busy) return;
    setText("");
    onSend(v);
  };

  const toggleMic = () => {
    const SR =
      (window as unknown as { SpeechRecognition?: new () => SpeechRec; webkitSpeechRecognition?: new () => SpeechRec })
        .SpeechRecognition ||
      (window as unknown as { webkitSpeechRecognition?: new () => SpeechRec }).webkitSpeechRecognition;
    if (!SR) {
      alert("Voice input isn't supported in this browser.");
      return;
    }
    if (listening) {
      recRef.current?.stop();
      return;
    }
    const rec = new SR();
    rec.lang = "en-US";
    rec.interimResults = false;
    rec.continuous = false;
    rec.onresult = (e) => {
      const said = e.results[0][0].transcript;
      setText(said);
      submit(said);
    };
    rec.onerror = () => {};
    rec.onend = () => {
      setListening(false);
      onListening(false);
      recRef.current = null;
    };
    recRef.current = rec;
    setListening(true);
    onListening(true);
    rec.start();
  };

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      {/* transcript */}
      <div className="min-h-0 flex-1 space-y-3 overflow-auto pr-1">
        <AnimatePresence initial={false}>
          {messages.map((m, i) => (
            <motion.div
              key={i}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3 }}
              className={m.role === "user" ? "flex justify-end" : "flex justify-start"}
            >
              <div
                className={
                  m.role === "user"
                    ? "max-w-[85%] rounded-md border border-cyan/30 bg-cyan/5 px-3 py-2 text-sm text-ink"
                    : "max-w-[90%] border-l-2 border-cyan px-3 py-1 text-[0.95rem] leading-relaxed text-cyan-bright"
                }
              >
                {m.role === "assistant" && (
                  <span className="label mb-0.5 block text-[0.55rem] text-cyan-dim">EDITH</span>
                )}
                <span className="whitespace-pre-wrap">{m.content}</span>
              </div>
            </motion.div>
          ))}
        </AnimatePresence>

        {busy && (
          <div className="flex items-center gap-2 px-3 text-cyan">
            <span className="label text-[0.55rem] text-cyan-dim">EDITH</span>
            <span className="flex gap-1">
              {[0, 1, 2].map((i) => (
                <span
                  key={i}
                  className="h-1.5 w-1.5 rounded-full bg-cyan"
                  style={{ animation: `core-pulse 0.9s ease-in-out ${i * 0.15}s infinite` }}
                />
              ))}
            </span>
          </div>
        )}
        <div ref={endRef} />
      </div>

      {/* input */}
      <div className="mt-3 flex items-center gap-2 border-t border-[var(--edge)] pt-3">
        <button
          onClick={toggleMic}
          title="Voice input"
          className="grid h-9 w-9 shrink-0 place-items-center rounded-full border transition"
          style={{
            borderColor: listening ? "#37f5a5" : "var(--edge-strong)",
            boxShadow: listening ? "0 0 14px #37f5a5" : "none",
            color: listening ? "#37f5a5" : "#38e1ff",
          }}
        >
          <span className={listening ? "animate-blink" : ""}>🎙</span>
        </button>
        <input
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && submit()}
          placeholder="Speak or type a command, Ahmed…"
          disabled={busy}
          className="mono flex-1 rounded border border-[var(--edge)] bg-black/30 px-3 py-2 text-sm text-ink placeholder:text-ink-mute focus:border-cyan/60 focus:outline-none focus:ring-1 focus:ring-cyan/40"
        />
        <button
          onClick={() => submit()}
          disabled={busy}
          className="label rounded border border-cyan px-4 py-2 text-cyan transition hover:bg-cyan/10 hover:glow-cyan disabled:opacity-40"
        >
          Send
        </button>
      </div>
    </div>
  );
}
