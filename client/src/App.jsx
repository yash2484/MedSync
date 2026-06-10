import UploadPanel from "./pages/UploadPanel.jsx";

// Phase 1 ships only the upload + pipeline-status view.
// PatientRegistry / TriageQueue / PatientDetail routing is wired in Phase 3.
export default function App() {
  return (
    <div className="min-h-screen bg-slate-50 text-slate-900">
      <header className="border-b bg-white px-6 py-4">
        <h1 className="text-xl font-semibold">MedSync</h1>
        <p className="text-sm text-slate-500">FHIR ingestion &amp; pipeline monitor</p>
      </header>
      <main className="mx-auto max-w-3xl p-6">
        <UploadPanel />
      </main>
    </div>
  );
}
