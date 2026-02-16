"use client";

import { useState, useCallback, useEffect } from "react";
import type { HealthResponse } from "@/types/search.types";

export type HealthStatus = "connected" | "degraded" | "disconnected" | "checking";

export function useHealthCheck(intervalMs = 30_000) {
  const [status, setStatus] = useState<HealthStatus>("checking");

  const check = useCallback(async () => {
    try {
      const res = await fetch("/api/health");
      if (!res.ok) {
        setStatus("disconnected");
        return;
      }
      const data: HealthResponse = await res.json();
      if (data.status === "ok") {
        setStatus(data.graph_connected === false ? "degraded" : "connected");
      } else if (data.status === "degraded") {
        setStatus("degraded");
      } else {
        setStatus("disconnected");
      }
    } catch {
      setStatus("disconnected");
    }
  }, []);

  useEffect(() => {
    check();
    const interval = setInterval(check, intervalMs);
    return () => clearInterval(interval);
  }, [check, intervalMs]);

  return status;
}
