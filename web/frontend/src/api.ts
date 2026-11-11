// Typed thin client over the FastAPI bridge. All paths are same-origin /api/*
// (Vite proxies to :8000 in dev; FastAPI serves the build in production).

export type Role = "user" | "assistant";
export interface Msg {
  role: Role;
  content: string;
}

export interface Status {
  name: string;
  city: string;
  claude: boolean;
  local: boolean;
  google: boolean;
  notion: boolean;
  tavily: boolean;
  news: boolean;
}

export interface SystemStats {
  cpu_pct: number;
  ram_pct: number;
  ram_used_gb: number;
  ram_total_gb: number;
  battery: { pct: number; charging: boolean } | null;
  uptime_str: string | null;
  summary: string;
}

export interface Weather {
  city: string;
  available: boolean;
  summary?: string;
  desc?: string;
  temp_c?: string;
  temp_f?: string;
  feels_c?: string;
  humidity?: string;
}

export interface Task {
  id: number;
  text: string;
  priority: "low" | "normal" | "high";
  done: boolean;
}

export interface CalEvent {
  id: string;
  summary: string;
  start: string;
  location: string;
}

export interface Email {
  id: string;
  sender: string;
  subject: string;
  snippet: string;
}

export interface Confirm {
  id: string;
  title: string;
  detail: string;
}

export interface Match {
  home: string;
  away: string;
  detail: string;
  state: "upcoming" | "live" | "finished" | string;
}
export interface Competition {
  status: string;
  matches: Match[];
}
export interface Football {
  premier_league?: Competition;
}

export interface Announcement {
  id: string;
  kind: "briefing" | "end_of_day" | "alert" | string;
  text: string;
  at: string;
}

export interface AgentInfo {
  id: string;
  label: string;
  description: string;
  tools: string[];
  tool_count: number;
}

export interface PrayerTime {
  name: string;
  time: string;
  next: boolean;
}
export interface Prayer {
  available: boolean;
  city?: string;
  times: PrayerTime[];
}

async function get<T>(path: string): Promise<T> {
  const r = await fetch(`/api${path}`);
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
  return r.json();
}
async function post<T>(path: string, body?: unknown): Promise<T> {
  const r = await fetch(`/api${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!r.ok) {
    let detail = `${r.status}`;
    try {
      detail = (await r.json()).detail ?? detail;
    } catch {
      /* ignore */
    }
    throw new Error(detail);
  }
  return r.json();
}

export const api = {
  status: () => get<Status>("/status"),
  system: () => get<SystemStats>("/system"),
  weather: () => get<Weather>("/weather"),
  news: () => get<{ headlines: string[] }>("/news?count=6"),
  tasks: () => get<{ tasks: Task[]; pending: number; done_today: number }>("/tasks"),
  addTask: (text: string, priority = "normal") =>
    post<Task>("/tasks", { text, priority }),
  completeTask: (id: number) => post<Task>(`/tasks/${id}/complete`),
  deleteTask: (id: number) =>
    fetch(`/api/tasks/${id}`, { method: "DELETE" }).then((r) => r.json()),
  calendar: () => get<{ connected: boolean; events: CalEvent[] }>("/calendar"),
  inbox: () =>
    get<{ connected: boolean; unread: number; emails: Email[] }>("/inbox"),
  briefing: () => get<{ text: string }>("/briefing"),
  chat: (messages: Msg[], backend: string) =>
    post<{ reply: string }>("/chat", { messages, backend }),
  confirms: () => get<Confirm[]>("/confirms"),
  resolveConfirm: (id: string, approve: boolean) =>
    post<{ ok: boolean }>(`/confirms/${id}`, { approve }),
  football: () => get<{ data: Football | null; loading: boolean; error: string | null }>("/football"),
  prayer: () => get<Prayer>("/prayer"),
  agents: () => get<{ agents: AgentInfo[]; activity: Record<string, string> }>("/agents"),
  announcements: (since?: string) =>
    get<{ announcements: Announcement[] }>(
      "/announcements" + (since ? `?since=${encodeURIComponent(since)}` : ""),
    ),
};
