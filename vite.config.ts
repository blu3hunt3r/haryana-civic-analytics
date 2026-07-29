import { defineConfig } from "vite";

export default defineConfig({
  base: "/",
  build: {
    target: "es2022",
    sourcemap: true,
    cssCodeSplit: true,
    rollupOptions: {
      output: {
        manualChunks: {
          maps: ["maplibre-gl"],
          charts: [
            "echarts/core",
            "echarts/charts",
            "echarts/components",
            "echarts/renderers"
          ]
        }
      }
    }
  }
});
