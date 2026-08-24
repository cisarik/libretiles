import path from "node:path";
import { defineConfig } from "vitest/config";

export default defineConfig({
  // Keep tests from loading frontend/.env.local (server secrets).
  envDir: path.join(__dirname, "src/lib"),
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  test: {
    environment: "node",
  },
});
