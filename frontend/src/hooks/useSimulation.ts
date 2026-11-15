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
const MAX_SAMPLES = 7200;
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

/** Human message for a failure to obtain a session. */
function backendError(e: unknown): string {
  if (e instanceof ApiError && e.status === 503) return `The SubseaSim server is busy: ${e.message}. Please try again shortly.`;
  if (e instanceof ApiError) return `The SubseaSim server refused the request: ${e.message}`;
  return `Cannot reach the SubseaSim server (${(e as Error).message}). Check that the backend is running.`;
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
  /** Informational message (e.g. session recovered after a server restart). */
  notice: string | null;
  clearNotice: () => void;
  notify: (msg: string | null) => void;
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
  const [notice, setNotice] = useState<string | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const recovering = useRef<Promise<string | null> | null>(null);

  const applyPayload = useCallback((p: SessionPayload) => {
    // Delta updates omit static scenario data (layout, presets, chemical
    // config); keep the last full values until the next full payload.
    setState((prev) =>
      p.state.layout || !prev || prev.scenario.id !== p.state.scenario.id
        ? p.state
        : {
            ...p.state,
            training_rules: p.state.training_rules ?? prev.training_rules,
            integrity_presets: p.state.integrity_presets ?? prev.integrity_presets,
            chemical_config: p.state.chemical_config ?? prev.chemical_config,
          },
    );
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

  /**
   * The server no longer knows our session (it restarted, or the session
   * expired). Start a fresh one and say so. Concurrent callers share one
   * recovery. Returns the new session id (null if the backend is unreachable).
   */
  const recoverSession = useCallback((): Promise<string | null> => {
    if (recovering.current) return recovering.current;
    recovering.current = (async () => {
      try {
        try {
          localStorage.removeItem(SESSION_KEY);
        } catch {
          /* ignore */
        }
        const p = await api.createSession();
        storeSession(p.session_id);
        setSamples([]);
        setEvents([]);
        applyPayload(p);
        setSessionId(p.session_id);
        setNotice("The simulation server was restarted, so your previous run was lost. A new session has started from the scenario's initial conditions.");
        return p.session_id;
      } catch (e) {
        setConnection("offline");
        setError(backendError(e));
        return null;
      } finally {
        recovering.current = null;
      }
    })();
    return recovering.current;
  }, [applyPayload]);

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
          setError(backendError(e));
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
      ws.onmessage = (ev) => {
        try {
          onMessage(JSON.parse(ev.data) as WsMessage);
        } catch (e) {
          console.error("SubseaSim: could not process a server update", e);
        }
      };
      ws.onclose = (ev) => {
        clearInterval(ping);
        if (closed) return;
        if (ev.code === 4404) {
          recoverSession();
          return;
        }
        setConnection("reconnecting");
        retry += 1;
        // A failed reconnect may mean the server restarted and forgot this
        // session: ask the REST API, which answers unambiguously with 404.
        if (retry >= 2) {
          api.getSession(sessionId).catch((e) => {
            if (!closed && e instanceof ApiError && e.status === 404) recoverSession();
          });
        }
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
  }, [sessionId, onMessage, recoverSession]);

  const run = useCallback(
    async (fn: (sid: string) => Promise<SessionPayload>) => {
      if (!sessionId) return false;
      try {
        applyPayload(await fn(sessionId));
        setError(null);
        return true;
      } catch (e) {
        if (e instanceof ApiError && e.status === 404 && /session/i.test(e.message)) {
          // session lost (server restart): recover, then retry the operation once
          const sid = await recoverSession();
          if (!sid) return false;
          try {
            applyPayload(await fn(sid));
            setError(null);
            return true;
          } catch (e2) {
            setError((e2 as Error).message);
            return false;
          }
        }
        setError((e as Error).message);
        return false;
      }
    },
    [sessionId, applyPayload, recoverSession],
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
    notice,
    clearNotice: () => setNotice(null),
    notify: setNotice,
    run,
  };
}
