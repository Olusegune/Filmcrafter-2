import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import { ErrorBoundary } from "./ErrorBoundary";
import { applyScale } from "./uiScale";
import "./focus.css";
import "./polish.css";             // the rhythm of every sheet: space, quiet status, one loud action
import "./corners.css";            // last, so that it has the final word on corners

async function boot() {
  if (import.meta.env.DEV && new URLSearchParams(location.search).has("mock")) {
    await (await import("./devmock")).installMock();
  }
  await applyScale();   // big screens and TVs: scale the interface before the first paint
  ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
    <React.StrictMode>
      <ErrorBoundary><App /></ErrorBoundary>
    </React.StrictMode>,
  );
}
boot();
