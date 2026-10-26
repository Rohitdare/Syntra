"use client";

import { useEffect, useState } from "react";
import { env } from "@/lib/config";
import { HealthResponse, HealthResponseSchema } from "@/lib/api/schemas";

type HealthState =
  | { status: "loading" }
  | { status: "success"; data: HealthResponse }
  | { status: "error"; message: string };

export default function Home() {
  const [health, setHealth] = useState<HealthState>({ status: "loading" });

  useEffect(() => {
    async function checkHealth() {
      try {
        const res = await fetch(`${env.NEXT_PUBLIC_API_BASE_URL}/api/health`, {
          headers: {
            "Accept": "application/json",
          },
        });
        if (!res.ok) {
          throw new Error(`Server returned HTTP ${res.status}`);
        }
        const json = await res.json();
        const parsed = HealthResponseSchema.parse(json);
        setHealth({ status: "success", data: parsed });
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : "Failed to connect to API server";
        setHealth({ status: "error", message: msg });
      }
    }

    checkHealth();
  }, []);

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col items-center justify-center p-6">
      <main className="w-full max-w-xl bg-slate-900 border border-slate-800 rounded-2xl p-8 shadow-2xl space-y-6">
        <header className="space-y-2 text-center">
          <h1 className="text-3xl font-bold tracking-tight text-white">Research Desk</h1>
          <p className="text-slate-400 text-sm">
            Multi-agent research assistant &bull; Stage 0 Environment
          </p>
        </header>

        <section className="bg-slate-950/80 rounded-xl p-6 border border-slate-800/80 space-y-4">
          <h2 className="text-xs font-semibold uppercase tracking-wider text-slate-400">
            System Connectivity
          </h2>

          <div className="flex items-center justify-between py-2 border-b border-slate-800">
            <span className="text-sm font-medium text-slate-300">FastAPI Backend</span>
            {health.status === "loading" && (
              <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-slate-800 text-slate-300 animate-pulse">
                Checking...
              </span>
            )}
            {health.status === "success" && (
              <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-emerald-950 text-emerald-400 border border-emerald-800">
                &bull; API reachable
              </span>
            )}
            {health.status === "error" && (
              <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-rose-950 text-rose-400 border border-rose-800">
                &times; API unreachable
              </span>
            )}
          </div>

          {health.status === "error" && (
            <div className="p-3 bg-rose-950/50 border border-rose-900/50 rounded-lg text-xs text-rose-300">
              <span className="font-semibold">Connection Error:</span> {health.message}
            </div>
          )}

          {health.status === "success" && (
            <div className="space-y-2 pt-2">
              <p className="text-xs text-slate-400">Service Configuration (Stage 0):</p>
              <div className="grid grid-cols-3 gap-2">
                <div className="p-2 rounded bg-slate-900 border border-slate-800 text-center">
                  <div className="text-[11px] text-slate-400">Gemini</div>
                  <div className="text-xs font-semibold text-slate-300">
                    {health.data.configured.gemini ? "Configured" : "Unset"}
                  </div>
                </div>
                <div className="p-2 rounded bg-slate-900 border border-slate-800 text-center">
                  <div className="text-[11px] text-slate-400">PostgreSQL</div>
                  <div className="text-xs font-semibold text-slate-300">
                    {health.data.configured.postgres ? "Configured" : "Unset"}
                  </div>
                </div>
                <div className="p-2 rounded bg-slate-900 border border-slate-800 text-center">
                  <div className="text-[11px] text-slate-400">Qdrant</div>
                  <div className="text-xs font-semibold text-slate-300">
                    {health.data.configured.qdrant ? "Configured" : "Unset"}
                  </div>
                </div>
              </div>
            </div>
          )}
        </section>

        <footer className="text-center text-xs text-slate-500">
          Target API: <code className="text-slate-400 font-mono">{env.NEXT_PUBLIC_API_BASE_URL}</code>
        </footer>
      </main>
    </div>
  );
}
