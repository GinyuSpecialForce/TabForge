import localFont from "next/font/local";

/**
 * Zen Kaku Gothic New (latin subset, SIL OFL) self-hosted from src/fonts —
 * the Quiet Paper typeface, vendored so every machine renders identically
 * without CDN calls. Hiragino Sans stays as the macOS fallback.
 */
export const zenKaku = localFont({
  src: [
    {
      path: "../fonts/zen-kaku-gothic-new-300.woff2",
      weight: "300",
      style: "normal",
    },
    {
      path: "../fonts/zen-kaku-gothic-new-400.woff2",
      weight: "400",
      style: "normal",
    },
    {
      path: "../fonts/zen-kaku-gothic-new-500.woff2",
      weight: "500",
      style: "normal",
    },
    {
      path: "../fonts/zen-kaku-gothic-new-700.woff2",
      weight: "700",
      style: "normal",
    },
  ],
  display: "swap",
  variable: "--font-zen",
});
