import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { QueryClientProvider } from "@tanstack/react-query";
import "./styles/globals.css";
import { queryClient } from "@/lib/queries";
import { startClock } from "@/lib/store";
import App from "./app";

startClock();
// Canvas text uses Inter and Source Code Pro: wait for them so the first frame is right.
const fontsReady = document.fonts?.load
  ? Promise.all([document.fonts.load('500 12px "Inter Variable"'), document.fonts.load('500 12px "Source Code Pro Variable"'),
      document.fonts.load('400 30px "Instrument Serif"')]).catch(() => undefined)
  : Promise.resolve();

fontsReady.finally(() => {
  createRoot(document.getElementById("root")!).render(
    <StrictMode>
      <QueryClientProvider client={queryClient}>
        <App />
      </QueryClientProvider>
    </StrictMode>,
  );
});
