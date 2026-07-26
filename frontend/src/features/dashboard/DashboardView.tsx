import { Activity, HeartPulse, RefreshCw } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { api } from "../../api";
import type { ScreenProps } from "../../app/types";
import type { DeepHealthResponse, StatsResponse } from "../../types";
import { displayStatus, humanizeIdentifier, statusLine } from "../../components/format";
import { IconButton, Metric, Panel, PanelTitle } from "../../components/ui";

const CHECK_NAMES: Record<string, string> = {
  db: "Database",
  llm: "LLM",
  vector: "Vector index",
  article_fetch: "Article fetch",
  voice_archive: "Voice archive",
  graph: "Memory graph",
};

export function DashboardView({ token, run }: ScreenProps) {
  const [stats, setStats] = useState<StatsResponse | null>(null);
  const [health, setHealth] = useState<DeepHealthResponse | null>(null);

  const load = useCallback(async () => {
    const [nextStats, nextHealth] = await Promise.all([
      run(() => api.status(token)),
      run(() => api.deepHealth(token)),
    ]);
    if (nextStats) setStats(nextStats);
    if (nextHealth) setHealth(nextHealth);
  }, [run, token]);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <section className="content-grid">
      <div className="metric-grid">
        <Metric label="Entries" value={stats?.raw_entries ?? 0} />
        <Metric label="Memories" value={stats?.memories ?? 0} />
        <Metric label="Entities" value={stats?.entities ?? 0} />
        <Metric label="Sources" value={stats?.sources ?? 0} />
        <Metric label="Processing" value={health?.checks.jobs ? statusLine(health.checks.jobs) : "unknown"} />
      </div>
      <div className="module-grid two-pane">
        <Panel>
          <PanelTitle icon={<HeartPulse size={18} />} title="System Health" action={<IconButton onClick={load} aria-label="Refresh runtime" title="Refresh runtime"><RefreshCw size={17} /></IconButton>} />
          <div className="health-list">
            {Object.entries(health?.checks || {}).map(([key, check]) => {
              const state = healthState(check.status);
              return (
                <div className="health-row" key={key}>
                  <span className="health-name">{CHECK_NAMES[key] || humanizeIdentifier(key)}</span>
                  <span className={`health-state ${state.tone}`}>
                    <span className="health-dot" aria-hidden="true" />
                    {state.label}
                  </span>
                </div>
              );
            })}
          </div>
        </Panel>
        <Panel>
          <PanelTitle icon={<Activity size={18} />} title="System" />
          <dl className="system-facts">
            <div>
              <dt>API version</dt>
              <dd>{health?.version || "unknown"}</dd>
            </div>
            <div>
              <dt>Uptime</dt>
              <dd>{`${Math.round(health?.uptime_seconds || stats?.uptime_seconds || 0)}s`}</dd>
            </div>
            <div>
              <dt>Vault files</dt>
              <dd>{stats?.vault_files ?? 0}</dd>
            </div>
          </dl>
        </Panel>
      </div>
    </section>
  );
}

function healthState(status: unknown): { tone: "good" | "work" | "bad"; label: string } {
  const value = String(status || "").trim().toLowerCase();
  if (value === "ok") return { tone: "good", label: "OK" };
  if (["healthy", "up", "ready", "configured", "enabled"].includes(value)) return { tone: "good", label: displayStatus(value) };
  if (["warn", "warning", "degraded"].includes(value)) return { tone: "work", label: "Degraded" };
  if (!value) return { tone: "bad", label: "Down" };
  return { tone: "bad", label: displayStatus(value) };
}
