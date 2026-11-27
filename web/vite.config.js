import { defineConfig } from "vite";
import { VitePWA } from "vite-plugin-pwa";

const base = process.env.PAGES_BASE || "/";

export default defineConfig({
  base,
  plugins: [
    VitePWA({
      registerType: "autoUpdate",
      includeAssets: ["icons/*.png", "models/*.task", "mediapipe/wasm/*"],
      manifest: {
        name: "Star Pop",
        short_name: "Star Pop",
        description: "Pop stars and dodge meteors with your body, using the camera.",
        theme_color: "#080c1c",
        background_color: "#080c1c",
        display: "standalone",
        orientation: "any",
        start_url: ".",
        scope: ".",
        icons: [
          { src: "icons/icon-192.png", sizes: "192x192", type: "image/png", purpose: "any" },
          { src: "icons/icon-512.png", sizes: "512x512", type: "image/png", purpose: "any" },
          {
            src: "icons/icon-maskable-512.png",
            sizes: "512x512",
            type: "image/png",
            purpose: "maskable",
          },
        ],
      },
      workbox: {
        globPatterns: ["**/*.{js,css,html,svg,png,webmanifest,wasm,task}"],
        maximumFileSizeToCacheInBytes: 15 * 1024 * 1024,
        navigateFallback: "index.html",
      },
      devOptions: { enabled: false },
    }),
  ],
});
