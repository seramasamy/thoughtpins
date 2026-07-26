import { ClipboardList, RefreshCw } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { api } from "../../api";
import type { ScreenProps } from "../../app/types";
import type { JobsPageResponse, JobStatus } from "../../types";
import { displayStatus, formatDate } from "../../components/format";
import { EmptyState, IconButton, Panel, PanelTitle, statusClass } from "../../components/ui";

const JOB_STATUSES = ["", "pending", "retry", "queued", "running", "completed", "failed", "dead_letter", "canceled"];

export function JobsView({ token, run }: ScreenProps) {
  const [status, setStatus] = useState("");
  const [jobs, setJobs] = useState<JobsPageResponse | null>(null);

  const load = useCallback(async () => {
    const result = await run(() => api.jobs(token, status));
    if (result) setJobs(result);
  }, [run, status, token]);

  useEffect(() => {
    void load();
  }, [load]);

  const action = async (jobId: string, kind: "retry" | "cancel") => {
    const result = await run(
      () => (kind === "retry" ? api.retryJob(token, jobId) : api.cancelJob(token, jobId)),
      kind === "retry" ? "Processing retry queued" : "Processing canceled",
    );
    if (result) void load();
  };

  return (
    <Panel>
      <PanelTitle
        icon={<ClipboardList size={18} />}
        title="Activity"
        action={<IconButton onClick={load} aria-label="Refresh activity" title="Refresh activity"><RefreshCw size={17} /></IconButton>}
      />
      <p className="muted">Background processing for saved entries, article imports, retries, and failures. Most users only need this if something is stuck.</p>
      <div className="toolbar">
        <select value={status} onChange={(event) => setStatus(event.target.value)} aria-label="Activity status">
          {JOB_STATUSES.map((item) => <option key={item} value={item}>{item || "all"}</option>)}
        </select>
      </div>
      {jobs !== null && jobs.items.length === 0 && (
        <EmptyState title="No activity yet" detail="Background saves, imports, and retries will appear here." />
      )}
      {(jobs?.items.length ?? 0) > 0 && (
        <div className="table-wrap jobs-table-wrap">
          <table className="jobs-table">
            <thead>
              <tr>
                <th>Status</th>
                <th>Task</th>
                <th>Entry</th>
                <th>Updated</th>
                <th className="right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {(jobs?.items || []).map((job) => (
                <tr key={job.id}>
                  <td data-label="Status"><JobStatusPill status={job.status} /></td>
                  <td data-label="Task"><code className="job-id" title={job.id}>{job.id}</code></td>
                  <td data-label="Entry">{job.entry_id ? <code className="job-id" title={job.entry_id}>{job.entry_id}</code> : "none"}</td>
                  <td data-label="Updated">{formatDate(job.finished_at_utc || job.started_at_utc || job.queued_at_utc || job.created_at_utc)}</td>
                  <td className="row-actions job-actions-cell">
                    <button className="quiet-button" type="button" onClick={() => action(job.id, "retry")} disabled={!isRetryable(job.status)}>Retry</button>
                    <button className="quiet-button danger" type="button" onClick={() => action(job.id, "cancel")} disabled={!isCancelable(job.status)}>Cancel</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Panel>
  );
}

function JobStatusPill({ status }: { status: JobStatus }) {
  return (
    <span className={`status with-dot ${statusClass(status)}`}>
      <span className="status-dot" aria-hidden="true" />
      {displayStatus(status)}
    </span>
  );
}

function isRetryable(status: JobStatus) {
  return ["failed", "dead_letter", "retry"].includes(status);
}

function isCancelable(status: JobStatus) {
  return ["pending", "retry", "queued"].includes(status);
}
