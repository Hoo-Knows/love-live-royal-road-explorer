import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  base: "./",
  plugins: [react()],
  server: {
    watch: {
      ignored: [
        "**/.cache/**",
        "**/.ruff_cache/**",
        "**/.uv-cache/**",
        "**/.venv/**",
        "**/chord_recognition_module/**",
        "**/data/raw/**",
        "**/data/analysis-manifest.json",
      ],
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: "./tests/setup.ts",
    css: true,
    globals: true,
    pool: "threads",
    maxWorkers: 1,
    fileParallelism: false
  }
});
