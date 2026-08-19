import { useEffect, useRef } from "react";
import { api } from "@/lib/api";

const KEY = "pokecoins_tracked_session";

/** Fires one lightweight visit ping per browser session. */
export function useVisitTracker() {
  const sent = useRef(false);

  useEffect(() => {
    if (sent.current || sessionStorage.getItem(KEY)) return;
    sent.current = true;
    sessionStorage.setItem(KEY, "1");
    api.post("/track").catch(() => {});
  }, []);
}
