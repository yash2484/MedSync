import { useState } from "react";
import PipelineStatus from "../components/PipelineStatus.jsx";

// Drag-and-drop FHIR Bundle upload with live pipeline progress.
export default function UploadPanel() {
  const [runId, setRunId] = useState(null);
  const [error, setError] = useState(null);

  async function upload(file) {
    setError(null);
    const body = new FormData();
    body.append("file", file);
    try {
      const res = await fetch("/api/v1/bundles/upload", { method: "POST", body });
      if (!res.ok) throw new Error(`Upload failed (${res.status})`);
      const data = await res.json();
      setRunId(data.pipeline_run_id);
    } catch (e) {
      setError(e.message);
    }
  }

  return (
    <section className="space-y-4">
      <label
        className="flex h-40 cursor-pointer items-center justify-center rounded-lg border-2 border-dashed border-slate-300 bg-white text-slate-500 hover:border-slate-400"
        onDragOver={(e) => e.preventDefault()}
        onDrop={(e) => {
          e.preventDefault();
          if (e.dataTransfer.files[0]) upload(e.dataTransfer.files[0]);
        }}
      >
        <span>Drop a FHIR Bundle (.json) here, or click to choose</span>
        <input
          type="file"
          accept="application/json,.json"
          className="hidden"
          onChange={(e) => e.target.files[0] && upload(e.target.files[0])}
        />
      </label>
      {error && <p className="text-sm text-red-600">{error}</p>}
      {runId && <PipelineStatus runId={runId} />}
    </section>
  );
}
