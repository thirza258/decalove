import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import path from "path";
import fs from "fs";
import type { Plugin } from "vite";

/**
 * Dev-only fallback: if an /images/* request misses public/images/,
 * try serving it from ../game/images/ instead. This means the frontend
 * works with the game folder images even before generate_frontend_images.py
 * has been run.
 */
function gameImagesFallback(): Plugin {
  return {
    name: "game-images-fallback",
    configureServer(server) {
      server.middlewares.use((req, res, next) => {
        if (req.url?.startsWith("/images/")) {
          const publicPath = path.join(__dirname, "public", req.url);
          if (!fs.existsSync(publicPath)) {
            const gamePath = path.join(__dirname, "..", "game", req.url);
            if (fs.existsSync(gamePath)) {
              const ext = path.extname(gamePath).toLowerCase();
              const mimeTypes: Record<string, string> = {
                ".png": "image/png",
                ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
              };
              res.setHeader("Content-Type", mimeTypes[ext] || "application/octet-stream");
              fs.createReadStream(gamePath).pipe(res);
              return;
            }
          }
        }
        next();
      });
    },
  };
}

export default defineConfig({
  plugins: [react(), tailwindcss(), gameImagesFallback()],
  server: { port: 5173 },
});
