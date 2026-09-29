import { defineConfig } from "@playwright/test";

// Smoke + accessibility suite over a production build, served against the
// recorded backend in e2e/mock-api.mjs (no live backend or API keys needed).
// Build first with the mock URL inlined:
//   NEXT_PUBLIC_API_URL=http://127.0.0.1:8010 npm run build && npm run test:e2e
export default defineConfig({
  testDir: "e2e",
  timeout: 30_000,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["github"], ["list"]] : "list",
  use: { baseURL: "http://127.0.0.1:3100", viewport: { width: 1440, height: 900 } },
  webServer: [
    {
      command: process.env.MOCK_API_RECORD
        ? `node e2e/mock-api.mjs --record ${process.env.MOCK_API_RECORD}`
        : "node e2e/mock-api.mjs",
      url: "http://127.0.0.1:8010/api/themes",
      reuseExistingServer: false,
      stdout: "pipe",
    },
    { command: "npx next start -p 3100 -H 127.0.0.1", url: "http://127.0.0.1:3100", reuseExistingServer: false },
  ],
});
