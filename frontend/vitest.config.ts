import path from "node:path";
import { defineConfig } from "vitest/config";

/**
 * Only the pure logic in src/lib/ has tests (see src/lib/__tests__/) —
 * page/component rendering isn't covered here (see docs/phase-5-notes.md
 * for why). The alias mirrors tsconfig.json's "@/*" path so a future
 * test can still import a component/page module directly if needed.
 */
export default defineConfig({
  test: {
    environment: "node",
    include: ["src/**/*.test.ts"],
  },
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
});
