"use client";

import { useEffect, useRef, useState } from "react";
import { WS_BASE } from "./api";

export type WsStatus = "connecting" | "open" | "closed";

/**
 * Native WebSocket hook with auto-reconnect (exponential backoff capped at 5s).
 * `enabled` gates connection attempts — pass false while the backend is known
 * to be down to avoid useless connection churn. Never throws; malformed
 * messages are ignored.
 */
export function useWebSocket(
  path: string,
  onMessage: (data: unknown) => void,
  enabled: boolean = true,
): WsStatus {
  const [status, setStatus] = useState<WsStatus>("closed");
  const handlerRef = useRef(onMessage);

  useEffect(() => {
    handlerRef.current = onMessage;
  }, [onMessage]);

  useEffect(() => {
    if (!enabled) {
      setStatus("closed");
      return;
    }

    let ws: WebSocket | null = null;
    let disposed = false;
    let attempt = 0;
    let timer: ReturnType<typeof setTimeout> | undefined;

    const schedule = () => {
      if (disposed) return;
      const delay = Math.min(5000, 500 * 2 ** attempt);
      attempt += 1;
      timer = setTimeout(connect, delay);
    };

    const connect = () => {
      if (disposed) return;
      setStatus("connecting");
      try {
        ws = new WebSocket(`${WS_BASE}${path}`);
      } catch {
        schedule();
        return;
      }
      ws.onopen = () => {
        attempt = 0;
        if (!disposed) setStatus("open");
      };
      ws.onmessage = (ev) => {
        if (disposed) return;
        try {
          handlerRef.current(JSON.parse(String(ev.data)));
        } catch {
          // ignore malformed frames
        }
      };
      ws.onerror = () => {
        // close handler drives reconnection
      };
      ws.onclose = () => {
        if (!disposed) {
          setStatus("connecting");
          schedule();
        }
      };
    };

    connect();

    return () => {
      disposed = true;
      if (timer !== undefined) clearTimeout(timer);
      if (ws) {
        ws.onopen = null;
        ws.onmessage = null;
        ws.onerror = null;
        ws.onclose = null;
        try {
          ws.close();
        } catch {
          // already closed
        }
      }
    };
  }, [path, enabled]);

  return status;
}
