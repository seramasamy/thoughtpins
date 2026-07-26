import React from "react";
import { createRoot } from "react-dom/client";
import "@fontsource-variable/newsreader";
import "@fontsource-variable/source-sans-3";
import App from "./App";
import { registerAppShellServiceWorker } from "./core/serviceWorker";
import "./styles.css";

registerAppShellServiceWorker();

createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
