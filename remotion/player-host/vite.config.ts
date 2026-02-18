import path from "path";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  base: "/player/",
  resolve: {
    alias: {
      "@remotion-math": path.resolve(__dirname, "../src/MathExplanation.tsx"),
    },
  },
});
