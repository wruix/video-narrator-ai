import React from "react";
import ReactDOM from "react-dom/client";
import { initI18n } from "@vns/i18n";
import App from "./App";
import "./styles.css";

initI18n();

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
