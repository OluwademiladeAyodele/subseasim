/**
 * Session + live-state hook.
 *
 * The backend is authoritative: this hook only stores what the backend
 * sends (REST responses and WebSocket deltas). It never computes or
 * interpolates process values.
 */
import { useCallback, useEffect, useRef, useState } from "react";

import { api, ApiError } from "@/services/api";
import type { Layout, Sample, SessionPayload, SimEvent, SimulationState, TrainingState, WsMessage } from "@/types/simulation";

const SESSION_KEY = "subseasim.session";
const MAX_SAMPLES = 3600;
const MAX_EVENTS = 500;

export type Connection = "connecting" | "live" | "reconnecting" | "offline";

function readStoredSession(): string | null {
  try {
    return localStorage.getItem(SESSION_KEY);
  } catch {
    return null;
  }
}
function storeSession(sid: string) {
  try {
    localStorage.setItem(SESSION_KEY, sid);
  } catch {
    /* storage unavailable: session lasts for this page only */
  }
}

export interface Simulation {
  sessionId: string | null;
  state: SimulationState | null;
  layout: Layout | null;
  training: TrainingState | null;
  samples: Sample[];
  events: SimEvent[];
  connection: Connection;
  error: string | null;
  clearError: () => void;
  /** Run an API call against the current session; errors surface in `error`. */
  run: (fn: (sid: string) => Promise<SessionPayload>) => Promise<boolean>;
}

export function useSimulation(): Simulation {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [state, setState] = useState<SimulationState | null>(null);
  const [layout, setLayout] = useState<Layout | null>(null);
  const [training, setTraining] = useState<TrainingState | null>(null);
  const [samples, setSamples] = useState<Sample[]>([]);
  const [events, setEvents] = useState<SimEvent[]>([]);
  const [connection, setConnection] = useState<Connection>("connecting");
  const [error, setError] = useState<string | null>(null);
  const wsRef = useRef<WebSocket | null>(null);

  const applyPayload = useCallback((p: SessionPayload) => {
    setState(p.state);
    if (p.state.layout) setLayout(p.state.layout);
    setTraining(p.training);
  }, []);

  const onMessage = useCallback(
    (msg: WsMessage) => {
      applyPayload(msg);
      if (msg.type === "init") {
        setSamples(msg.samples.slice(-MAX_SAMPLES));
        setEvents(msg.events.slice(-MAX_EVENTS));
        return;
      }
      if (msg.samples.length) {
        setSamples((prev) => {
          const last = prev.length ? (prev[prev.length - 1].seq ?? 0) : 0;
          const fresh = msg.samples.filter((s) => (s.seq ?? 0) > last);
          return fresh.length ? [...prev, ...fresh].slice(-MAX_SAMPLES) : prev;
        });
      }
      if (msg.events.length) {
        setEvents((prev) => {
          const last = prev.length ? prev[prev.length - 1].id : 0;
          const fresh = msg.events.filter((e) => e.id > last);
          return fresh.length ? [...prev, ...fresh].slice(-MAX_EVENTS) : prev;
        });
      }
    },
    [applyPayload],
  );

  // establish session
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const stored = readStoredSession();
        let payload: SessionPayload | null = null;
        if (stored) {
          try {
            payload = await api.getSession(stored);
          } catch (e) {
            if (!(e instanceof ApiError && e.status === 404)) throw e;
          }
        }
        if (!payload) payload = await api.createSession();
        if (cancelled) return;
        storeSession(payload.session_id);
        applyPayload(payload);
        setSessionId(payload.session_id);
      } catch (e) {
        if (!cancelled) {
          setConnection("offline");
          setError(`Cannot reach the SubseaSim backend: ${(e as Error).message}`);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [applyPayload]);

  // websocket with reconnect
  useEffect(() => {
    if (!sessionId) return;
    let closed = false;
    let retry = 0;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let ping: ReturnType<typeof setInterval> | undefined;

    const connect = () => {
      const proto = window.location.protocol === "https:" ? "wss" : "ws";
      const ws = new WebSocket(`${proto}://${window.location.host}/ws/sessions/${sessionId}`);
      wsRef.current = ws;
      ws.onopen = () => {
        retry = 0;
        setConnection("live");
        ping = setInterval(() => ws.readyState === WebSocket.OPEN && ws.send("ping"), 20_000);
      };
      ws.onmessage = (ev) => onMessage(JSON.parse(ev.data) as WsMessage);
      ws.onclose = (ev) => {
        clearInterval(ping);
        if (closed) return;
        if (ev.code === 4404) {
          // session expired on the server: start a new one
          try {
            localStorage.removeItem(SESSION_KEY);
          } catch {
            /* ignore */
          }
          api.createSession().then((p) => {
            storeSession(p.session_id);
            applyPayload(p);
            setSessionId(p.session_id);
          });
          return;
        }
        setConnection("reconnecting");
        retry += 1;
        timer = setTimeout(connect, Math.min(10_000, 500 * 2 ** retry));
      };
    };
    connect();
    return () => {
      closed = true;
      clearTimeout(timer);
      clearInterval(ping);
      wsRef.current?.close();
    };
  }, [sessionId, onMessage, applyPayload]);

  const run = useCallback(
    async (fn: (sid: string) => Promise<SessionPayload>) => {
      if (!sessionId) return false;
      try {
        applyPayload(await fn(sessionId));
        setError(null);
        return true;
      } catch (e) {
        setError((e as Error).message);
        return false;
      }
    },
    [sessionId, applyPayload],
  );

  return {
    sessionId,
    state,
    layout,
    training,
    samples,
    events,
    connection,
    error,
    clearError: () => setError(null),
    run,
  };
}
