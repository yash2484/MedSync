import { useEffect, useRef, useState } from "react";

// Subscribe to pipeline status events for a given run.
// Emits the list of stage-transition messages received over the WebSocket.
export function usePipelineStatus(runId) {
  const [events, setEvents] = useState([]);
  const wsRef = useRef(null);

  useEffect(() => {
    if (!runId) return;
    const proto = window.location.protocol === "https:" ? "wss" : "ws";
    const ws = new WebSocket(`${proto}://${window.location.host}/api/v1/bundles/${runId}/status`);
    wsRef.current = ws;
    ws.onmessage = (e) => {
      try {
        setEvents((prev) => [...prev, JSON.parse(e.data)]);
      } catch {
        /* ignore malformed frame */
      }
    };
    return () => ws.close();
  }, [runId]);

  return events;
}
