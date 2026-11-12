import React from "react";
import { createRoot } from "react-dom/client";
import "./fonts.css";
import "./landing-font.css";
import App from "./App";
import "./styles.css";
import "./interface.css";
import "./workspace-panels.css";
import "./auth.css";
import "./schema.css";
import "./home.css";
import "./landing.css";
import "./notebook.css";
import "./light-theme.css";
import "./study.css";
import "./dark-theme.css";
createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
