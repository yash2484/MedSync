/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        // ESI acuity palette (1=red … 5=green) — used by TriageQueue in Phase 3.
        esi: {
          1: "#dc2626",
          2: "#f97316",
          3: "#eab308",
          4: "#22c55e",
          5: "#16a34a",
        },
      },
    },
  },
  plugins: [],
};
