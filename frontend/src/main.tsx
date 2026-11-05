import React from "react";
import { createRoot } from "react-dom/client";
import "@fontsource/be-vietnam-pro/400.css";
import "@fontsource/be-vietnam-pro/500.css";
import "@fontsource/be-vietnam-pro/600.css";
import App from "./App";
import "./styles.css";
import "./interface.css";
import "./workspace-panels.css";
import "./auth.css";
createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
