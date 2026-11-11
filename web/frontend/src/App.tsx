import { useCallback, useEffect, useRef, useState } from "react";
import { AnimatePresence } from "framer-motion";
import { api, type Confirm, type Msg, type Task } from "./api";
import { usePolling } from "./hooks";
import { useWakeWord } from "./useWakeWord";
import Background from "./components/Background";
import BootOverlay from "./components/BootOverlay";
import StatusBar from "./components/StatusBar";
import ArcReactorCore, { type CoreState } from "./components/ArcReactorCore";
import ChatDrawer from "./components/ChatDrawer";
import ConfirmModal from "./components/ConfirmModal";
import NewsTicker from "./components/NewsTicker";
import SystemPanel from "./components/panels/SystemPanel";
import WeatherPanel from "./components/panels/WeatherPanel";
import CalendarPanel from "./components/panels/CalendarPanel";
import InboxPanel from "./components/panels/InboxPanel";
import TasksPanel from "./components/panels/TasksPanel";
import FootballPanel from "./components/panels/FootballPanel";
import PrayerPanel from "./components/panels/PrayerPanel";
import AgentNetworkPanel from "./components/panels/AgentNetworkPanel";

function greeting(): string {
  const h = new Date().getHours();
  return h < 12 ? "Good morning" : h < 17 ? "Good afternoon" : "Good evening";
}

// Two-tone acknowledgement beep for the wake word. Uses Web Audio (not speech)
// so it never sets the "speaking" state — the wake listener keeps running and
// the pending command isn't lost.
let audioCtx: AudioContext | null = null;
function chime() {
  try {
    audioCtx =
      audioCtx || new (window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext)();
    const t = audioCtx.currentTime;
    [880, 1320].forEach((f, i) => {
      const o = audioCtx!.createOscillator();
      const g = audioCtx!.createGain();
      o.type = "sine";
      o.frequency.value = f;
      o.connect(g);
      g.connect(audioCtx!.destination);
      const s = t + i * 0.09;
      g.gain.setValueAtTime(0.0001, s);
      g.gain.exponentialRampToValueAtTime(0.16, s + 0.02);
      g.gain.exponentialRampToValueAtTime(0.0001, s + 0.13);
      o.start(s);
      o.stop(s + 0.14);
    });
  } catch {
    /* audio unavailable — silent */
  }
}

// Strip things that shouldn't be read aloud — emoji, markdown markers, bullets,
// stray symbols — while keeping normal punctuation (so "%" / "°" still speak as
// "percent" / "degrees"). This is what stops EDITH reading "star star" or emoji.
function cleanForSpeech(text: string): string {
  return text
    .replace(/[\u{1F000}-\u{1FAFF}]/gu, " ") // emoji & pictographs
    .replace(/[\u{2600}-\u{27BF}]/gu, " ") // misc symbols & dingbats
    .replace(/[\u{2190}-\u{21FF}\u{2B00}-\u{2BFF}]/gu, " ") // arrows
    .replace(/[️‍]/gu, "") // variation selectors / ZWJ
    .replace(/[*_`#>|~]/g, " ") // markdown emphasis / headers / code / rules
    .replace(/[•◆▪●·]/g, ", ") // bullets → a spoken pause
    .replace(/\s[–—]\s/g, ", ") // spaced en/em dashes → pause
    .replace(/[ \t]{2,}/g, " ")
    .replace(/ +([,.!?;:])/g, "$1")
    .trim();
}

// Pick a female voice. Gender comes first (never fall back to a British *man*),
// then British accent as a bonus. The Web Speech API doesn't expose gender, so
// we match on known voice names. Falls back to a female US voice (Samantha) over
// any male voice.
const FEMALE =
  /(female|woman|samantha|karen|moira|tessa|fiona|victoria|kate|serena|stephanie|martha|sonia|libby|hazel|amelia|allison|ava|susan|zoe|veena|zira|joana|luciana|paulina|catherine)/i;
const MALE =
  /(\bmale\b|daniel|alex|fred|tom|aaron|rishi|oliver|arthur|gordon|reed|rocko|eddy|grandpa|jacques|thomas|xander)/i;

function pickVoice(voices: SpeechSynthesisVoice[]): SpeechSynthesisVoice | undefined {
  const en = (v: SpeechSynthesisVoice) => /^en/i.test(v.lang);
  const gb = (v: SpeechSynthesisVoice) => /en-GB/i.test(v.lang);
  return (
    voices.find((v) => /google uk english female/i.test(v.name)) ||
    voices.find((v) => gb(v) && FEMALE.test(v.name)) || // British female
    voices.find((v) => en(v) && FEMALE.test(v.name)) || // any English female
    voices.find((v) => FEMALE.test(v.name)) || // any female
    voices.find((v) => /google us english/i.test(v.name)) || // female-voiced
    voices.find((v) => en(v) && !MALE.test(v.name)) || // English, not male
    voices.find((v) => !MALE.test(v.name)) ||
    voices[0]
  );
}

// Voices load asynchronously in Chrome; resolve the chosen one once ready so a
// too-early speak() doesn't fall back to the browser's default (often male).
let CHOSEN_VOICE: SpeechSynthesisVoice | null = null;
function resolveVoice() {
  if (!("speechSynthesis" in window)) return;
  const v = window.speechSynthesis.getVoices();
  if (v.length) CHOSEN_VOICE = pickVoice(v) ?? null;
}

// Speak with EDITH's real ElevenLabs voice, falling back to the browser's
// built-in synthesis if the key is missing, quota is gone, or the request
// fails — she is never left silent.
let currentAudio: HTMLAudioElement | null = null;

async function speak(text: string, onStart: () => void, onEnd: () => void) {
  window.speechSynthesis?.cancel();
  if (currentAudio) {
    currentAudio.pause();
    currentAudio = null;
  }
  const clean = cleanForSpeech(text);
  if (!clean) return onEnd();

  try {
    const r = await fetch("/api/voice/speak", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: clean }),
    });
    // 204 = voice unavailable → fall through to the browser voice.
    if (r.ok && r.status !== 204) {
      const url = URL.createObjectURL(await r.blob());
      const audio = new Audio(url);
      currentAudio = audio;
      audio.onplay = onStart;
      const finish = () => {
        URL.revokeObjectURL(url);
        if (currentAudio === audio) currentAudio = null;
        onEnd();
      };
      audio.onended = finish;
      audio.onerror = finish;
      await audio.play();
      return;
    }
  } catch {
    /* fall through to browser speech */
  }
  speakBrowser(text, onStart, onEnd);
}

// Browser speech synthesis fallback. Chrome silently cuts off utterances longer
// than ~15s, so split into chunks and queue them. onStart fires once.
function speakBrowser(text: string, onStart: () => void, onEnd: () => void) {
  if (!("speechSynthesis" in window)) return onEnd();
  const synth = window.speechSynthesis;
  synth.cancel();
  const clean = cleanForSpeech(text);
  // Group sentences into ~220-char chunks (still under Chrome's ~15s cutoff) so
  // there are fewer gaps between utterances — this keeps the delivery flowing.
  const sentences = clean.match(/[^.!?\n]+[.!?]?/g) ?? [clean];
  const chunks: string[] = [];
  let buf = "";
  for (const s of sentences) {
    const t = s.trim();
    if (!t) continue;
    if (buf && (buf + " " + t).length > 220) {
      chunks.push(buf);
      buf = t;
    } else {
      buf = buf ? buf + " " + t : t;
    }
  }
  if (buf) chunks.push(buf);

  const voice = CHOSEN_VOICE ?? pickVoice(synth.getVoices());
  let i = 0;
  let started = false;
  const next = () => {
    if (i >= chunks.length) return onEnd();
    const u = new SpeechSynthesisUtterance(chunks[i++]);
    u.rate = 1.08; // slightly brisker than default, not rushed
    u.pitch = 1.06; // natural, un-robotic
    if (voice) {
      u.voice = voice;
      u.lang = voice.lang;
    }
    if (!started) {
      started = true;
      onStart();
    }
    u.onend = next;
    u.onerror = next;
    synth.speak(u);
  };
  next();
}

// Desktop notification that works even when the tab is in the background.
// Deduped by key so a repeating poll can't spam the same alert.
const _notified = new Set<string>();
function notify(key: string, title: string, body: string) {
  if (_notified.has(key)) return;
  _notified.add(key);
  try {
    if (typeof Notification !== "undefined" && Notification.permission === "granted") {
      new Notification(title, { body, tag: key, icon: "/favicon.svg" });
    }
  } catch {
    /* notifications unavailable */
  }
}

export default function App() {
  const status = usePolling(api.status, 15000);
  const system = usePolling(api.system, 4000);
  const weather = usePolling(api.weather, 600000);
  const calendar = usePolling(api.calendar, 60000);
  const inbox = usePolling(api.inbox, 60000);
  const news = usePolling(api.news, 300000);
  const football = usePolling(api.football, 30000);
  const prayer = usePolling(api.prayer, 60000);
  // Poll fast so the network graph animates while specialists are working.
  const agentNet = usePolling(api.agents, 1500);

  // Tasks need instant refresh after mutations, so poll manually.
  const [tasks, setTasks] = useState<{ tasks: Task[]; pending: number; done_today: number } | null>(null);
  const reloadTasks = useCallback(async () => {
    try {
      setTasks(await api.tasks());
    } catch {
      /* keep last */
    }
  }, []);
  useEffect(() => {
    reloadTasks();
    const id = setInterval(reloadTasks, 6000);
    return () => clearInterval(id);
  }, [reloadTasks]);

  // Conversation + assistant state.
  const [messages, setMessages] = useState<Msg[]>([]);
  const [busy, setBusy] = useState(false);
  const [listening, setListening] = useState(false);
  const [speaking, setSpeaking] = useState(false);
  const [booted, setBooted] = useState(false);
  const [briefingText, setBriefingText] = useState<string | null>(null);
  const [wakeActive, setWakeActive] = useState(false);
  const [wakeCapturing, setWakeCapturing] = useState(false);
  const [chatOpen, setChatOpen] = useState(false);
  const [reactorSize, setReactorSize] = useState(460);
  const [brain, setBrain] = useState<"claude" | "local">(
    () => (localStorage.getItem("jarvis_brain") as "claude" | "local") || "local",
  );
  useEffect(() => localStorage.setItem("jarvis_brain", brain), [brain]);
  const voiceOn = useRef(true);

  // Scale the reactor to fill the (now dominant) left area, within the viewport.
  useEffect(() => {
    const calc = () => {
      const h = window.innerHeight;
      const w = window.innerWidth;
      setReactorSize(
        Math.max(300, Math.min(Math.round(h * 0.64), Math.round((w - 360) * 0.6), 660)),
      );
    };
    calc();
    window.addEventListener("resize", calc);
    return () => window.removeEventListener("resize", calc);
  }, []);

  const coreState: CoreState = listening || wakeCapturing
    ? "listening"
    : busy
    ? "thinking"
    : speaking
    ? "speaking"
    : "idle";

  // Restore the previous conversation, then append today's greeting + briefing.
  // The transcript is persisted below so a reload doesn't wipe the chat.
  useEffect(() => {
    let restored: Msg[] = [];
    try {
      const saved = localStorage.getItem("jarvis_chat");
      if (saved) restored = (JSON.parse(saved) as Msg[]).slice(-60);
    } catch {
      /* corrupt store — start fresh */
    }
    setMessages([
      ...restored,
      { role: "assistant", content: `${greeting()}, Ahmed. All systems online.` },
    ]);
    api
      .briefing()
      .then((b) => {
        setBriefingText(b.text);
        setMessages((m) => [...m, { role: "assistant", content: b.text }]);
      })
      .catch(() => {});
  }, []);

  // Persist the transcript (capped so localStorage can't grow unbounded).
  useEffect(() => {
    if (messages.length) {
      try {
        localStorage.setItem("jarvis_chat", JSON.stringify(messages.slice(-60)));
      } catch {
        /* quota — ignore */
      }
    }
  }, [messages]);

  // Resolve the female voice once Chrome finishes loading its voice list.
  useEffect(() => {
    resolveVoice();
    const synth = window.speechSynthesis;
    synth?.addEventListener?.("voiceschanged", resolveVoice);
    return () => synth?.removeEventListener?.("voiceschanged", resolveVoice);
  }, []);

  // Boot: user gesture unlocks audio, then EDITH speaks the briefing aloud and
  // the "Hey Edith" wake word goes live (Chrome will ask for mic access).
  const activate = useCallback(async () => {
    setBooted(true);
    setWakeActive(true);
    // The boot gesture is also our chance to ask for notification permission.
    try {
      if (typeof Notification !== "undefined" && Notification.permission === "default") {
        Notification.requestPermission();
      }
    } catch {
      /* unsupported */
    }
    let text = briefingText;
    if (!text) {
      try {
        text = (await api.briefing()).text;
      } catch {
        text = null;
      }
    }
    if (text && voiceOn.current) {
      speak(text, () => setSpeaking(true), () => setSpeaking(false));
    }
  }, [briefingText]);

  const send = useCallback(
    async (text: string) => {
      const next: Msg[] = [...messages, { role: "user", content: text }];
      setMessages(next);
      setBusy(true);
      try {
        const { reply } = await api.chat(next, brain);
        setMessages((m) => [...m, { role: "assistant", content: reply }]);
        if (voiceOn.current) speak(reply, () => setSpeaking(true), () => setSpeaking(false));
        reloadTasks();
      } catch (e) {
        const msg = (e as Error).message;
        const friendly = /credit balance|too low/i.test(msg)
          ? "I'm out of Claude credits, Ahmed — I can't think until you top up the balance at console.anthropic.com. The dashboard widgets still work."
          : `⚠ System fault: ${msg}`;
        setMessages((m) => [...m, { role: "assistant", content: friendly }]);
      } finally {
        setBusy(false);
      }
    },
    [messages, reloadTasks, brain],
  );

  // "Hey Edith" wake word. Paused while EDITH is speaking, thinking, or the
  // manual mic is open, so it never captures its own voice or double-listens.
  const paused = speaking || busy || listening;
  useWakeWord({
    active: wakeActive && booted && !paused,
    onWakeHeard: chime,
    onCommand: send,
    onCapturing: setWakeCapturing,
    onDenied: () => {
      setWakeActive(false);
      setMessages((m) => [
        ...m,
        {
          role: "assistant",
          content:
            '⚠ Microphone access is blocked, so the wake word is off. Allow the mic for this site in Chrome to use "Hey Edith".',
        },
      ]);
    },
  });

  // Desktop alerts: calendar events starting soon, and the next prayer.
  useEffect(() => {
    const soon = (iso: string) => {
      if (!iso.includes("T")) return -1;
      const mins = Math.round((new Date(iso).getTime() - Date.now()) / 60000);
      return mins;
    };
    for (const ev of calendar?.events ?? []) {
      const mins = soon(ev.start);
      if (mins > 0 && mins <= 10) {
        notify(`cal-${ev.id}`, "Calendar", `${ev.summary} starts in ${mins} min`);
      }
    }
  }, [calendar]);

  useEffect(() => {
    const next = prayer?.times.find((t) => t.next);
    if (!next) return;
    const [h, m] = next.time.split(":").map(Number);
    const t = new Date();
    t.setHours(h, m, 0, 0);
    const mins = Math.round((t.getTime() - Date.now()) / 60000);
    if (mins > 0 && mins <= 10) {
      notify(`prayer-${next.name}-${new Date().toDateString()}`, "Prayer", `${next.name} in ${mins} min`);
    }
  }, [prayer]);

  // Reminders fired by the backend.
  useEffect(() => {
    const id = setInterval(async () => {
      try {
        const list = await fetch("/api/reminders").then((r) => r.json());
        for (const r of list as { text: string; at: string }[]) {
          notify(`rem-${r.at}`, "Reminder", r.text);
        }
      } catch {
        /* ignore */
      }
    }, 20000);
    return () => clearInterval(id);
  }, []);

  // Scheduled announcements (auto briefing, end-of-day, calendar alerts).
  // These fire on the server whether or not the tab is focused; when we pick
  // one up EDITH speaks it, notifies, and drops it into the transcript.
  const lastAnnRef = useRef<string | undefined>(undefined);
  useEffect(() => {
    if (!booted) return; // don't speak before the audio gesture
    const id = setInterval(async () => {
      try {
        const { announcements } = await api.announcements(lastAnnRef.current);
        for (const a of announcements) {
          lastAnnRef.current = a.id;
          setMessages((m) => [...m, { role: "assistant", content: a.text }]);
          notify(
            `ann-${a.id}`,
            a.kind === "briefing" ? "Morning briefing"
              : a.kind === "end_of_day" ? "End of day" : "EDITH",
            a.text.slice(0, 140),
          );
          if (voiceOn.current) speak(a.text, () => setSpeaking(true), () => setSpeaking(false));
        }
      } catch {
        /* ignore */
      }
    }, 20000);
    return () => clearInterval(id);
  }, [booted]);

  // Poll for pending side-effect confirmations.
  const [confirm, setConfirm] = useState<Confirm | null>(null);
  useEffect(() => {
    const id = setInterval(async () => {
      try {
        const list = await api.confirms();
        setConfirm(list[0] ?? null);
      } catch {
        /* ignore */
      }
    }, 1200);
    return () => clearInterval(id);
  }, []);
  const decide = async (cid: string, approve: boolean) => {
    setConfirm(null);
    try {
      await api.resolveConfirm(cid, approve);
    } catch {
      /* ignore */
    }
  };

  return (
    <div className="relative flex h-screen flex-col">
      <Background />
      <StatusBar
        status={status}
        system={system}
        wake={{ active: wakeActive, capturing: wakeCapturing, onToggle: () => setWakeActive((v) => !v) }}
        onComms={() => setChatOpen((v) => !v)}
        brain={{ value: brain, onToggle: () => setBrain((b) => (b === "claude" ? "local" : "claude")) }}
      />

      <main className="relative z-10 grid min-h-0 flex-1 grid-cols-1 gap-3 p-3 lg:grid-cols-[1fr_340px]">
        {/* Reactor core — dominant focal point */}
        <section className="relative hidden min-h-0 flex-col items-center justify-center overflow-hidden lg:flex">
          <div className="mb-8 text-center">
            <div className="label text-ink-dim">{greeting()}, Ahmed</div>
            <h2 className="display mt-1 text-2xl tracking-[0.28em] text-cyan-bright glow-cyan">
              {coreState === "thinking"
                ? "PROCESSING…"
                : coreState === "listening"
                ? "LISTENING…"
                : coreState === "speaking"
                ? "RESPONDING…"
                : "STANDING BY"}
            </h2>
          </div>
          <ArcReactorCore size={reactorSize} state={coreState} />
          <div className="mt-10 flex items-center gap-8">
            {[
              ["CLAUDE", status?.claude],
              ["GOOGLE", status?.google],
              ["NOTION", status?.notion],
              ["SEARCH", status?.tavily],
            ].map(([k, on]) => (
              <div key={k as string} className="flex flex-col items-center gap-1">
                <span
                  className={`h-2 w-2 rounded-full ${on ? "bg-green" : "bg-ink-mute"}`}
                  style={on ? { boxShadow: "0 0 8px #37f5a5" } : undefined}
                />
                <span className="label text-[0.5rem] text-ink-dim">{k as string}</span>
              </div>
            ))}
          </div>
        </section>

        {/* All widgets — compact right sidebar */}
        <div className="min-h-0 space-y-3 overflow-y-auto pr-1">
          <FootballPanel
            data={football?.data ?? null}
            loading={football?.loading ?? true}
            error={football?.error}
            delay={0.05}
          />
          <AgentNetworkPanel
            agents={agentNet?.agents ?? []}
            activity={agentNet?.activity ?? {}}
            delay={0.06}
          />
          <PrayerPanel data={prayer} delay={0.08} />
          <WeatherPanel weather={weather} delay={0.1} />
          <SystemPanel system={system} delay={0.15} />
          <CalendarPanel data={calendar} delay={0.2} />
          <InboxPanel data={inbox} delay={0.25} />
          <TasksPanel data={tasks} reload={reloadTasks} delay={0.3} />
        </div>
      </main>

      <NewsTicker headlines={news?.headlines ?? []} />
      <ChatDrawer
        open={chatOpen}
        onToggle={() => setChatOpen((v) => !v)}
        messages={messages}
        busy={busy}
        onSend={send}
        onListening={setListening}
      />
      <ConfirmModal confirm={confirm} onDecide={decide} />
      <AnimatePresence>{!booted && <BootOverlay onActivate={activate} />}</AnimatePresence>
    </div>
  );
}
