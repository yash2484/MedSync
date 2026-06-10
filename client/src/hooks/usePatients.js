import { useCallback, useEffect, useState } from "react";

// Fetch the patient registry from the API. Expands with FHIR-native search in Phase 3.
export function usePatients() {
  const [patients, setPatients] = useState([]);
  const [loading, setLoading] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch("/api/v1/patients");
      setPatients(await res.json());
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return { patients, loading, refresh };
}
