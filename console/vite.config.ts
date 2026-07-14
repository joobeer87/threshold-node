import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

const loopbackProxy = {
  "/api": {
    target: "http://127.0.0.1:8471",
    changeOrigin: false,
    rewrite: (path: string) => path.replace(/^\/api/, ""),
  },
};

export default defineConfig({
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    port: 5173,
    strictPort: true,
    proxy: loopbackProxy,
  },
  preview: {
    host: "127.0.0.1",
    port: 4173,
    strictPort: true,
    proxy: loopbackProxy,
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    css: true,
  },
});
