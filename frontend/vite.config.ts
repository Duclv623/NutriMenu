import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
const ragTarget = process.env.RAG_PROXY_TARGET || "http://127.0.0.1:8000";
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      "/api": {
        target: process.env.API_PROXY_TARGET || "http://127.0.0.1:8080",
        changeOrigin: true,
      },
      "/rag": {
        target: ragTarget,
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/rag/, ""),
        configure(proxy) {
          proxy.on("proxyReq", (proxyRequest, request) => {
            // Only translate our development UI's origin. Preserve the chatbot's origin check.
            if (
              ["http://127.0.0.1:5173", "http://localhost:5173"].includes(
                request.headers.origin || "",
              )
            ) {
              proxyRequest.setHeader("Origin", new URL(ragTarget).origin);
            }
          });
        },
      },
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    clearMocks: true,
    env: { VITE_API_MODE: "demo", VITE_RAG_ENABLED: "false" },
  },
});
