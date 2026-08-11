import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import path from "node:path";

export default defineConfig({
  plugins: [react()],
  test: { environment: "jsdom", globals: true },
  resolve: {
    alias: {
      // "server-only" is a Next build-time marker: importing it from a client
      // component fails the build. That guard has no runtime behaviour, so the
      // test run aliases it away. The guard itself is asserted separately in
      // env-safety.test.ts, which checks the import is present in the source.
      "server-only": path.resolve(__dirname, "__tests__/stubs/server-only.ts"),
      "@": path.resolve(__dirname, "."),
    },
  },
});
