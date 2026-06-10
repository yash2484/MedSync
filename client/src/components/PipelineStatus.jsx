import { usePipelineStatus } from "../hooks/useWebSocket.js";

const STAGES = ["parse", "normalize", "deduplicate", "enrich"];

// Renders real-time stage progress for a pipeline run (CLAUDE.md §9.5).
export default function PipelineStatus({ runId }) {
  const events = usePipelineStatus(runId);
  const latestByStage = Object.fromEntries(events.map((e) => [e.stage, e.status]));

  return (
    <div className="rounded-lg border bg-white p-4">
      <p className="mb-3 text-sm font-medium">Pipeline run #{runId}</p>
      <ol className="space-y-2">
        {STAGES.map((stage) => {
          const status = latestByStage[stage] ?? "pending";
          return (
            <li key={stage} className="flex items-center justify-between text-sm">
              <span className="capitalize">{stage}</span>
              <span
                className={
                  status === "completed"
                    ? "text-green-600"
                    : status === "running"
                    ? "text-amber-600"
                    : status === "failed"
                    ? "text-red-600"
                    : "text-slate-400"
                }
              >
                {status}
              </span>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
