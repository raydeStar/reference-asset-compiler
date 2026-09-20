import { defineConfig } from "vite";
import { fileURLToPath } from "node:url";

export default defineConfig({
  base: "./",
  build: {
    rollupOptions: {
      input: {
        main: fileURLToPath(new URL("./index.html", import.meta.url)),
        review: fileURLToPath(new URL("./review.html", import.meta.url)),
      },
      output: { manualChunks: { three: ["three"] } },
    },
  },
});
