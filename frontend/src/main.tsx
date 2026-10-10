import { Component, StrictMode } from "react";
import type { ReactNode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import "./style.css";

class InterfaceBoundary extends Component<
  { children: ReactNode },
  { failed: boolean }
> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  render() {
    if (this.state.failed)
      return (
        <main className="startup-fallback" role="alert">
          <h1>&gt;_ VersionVerdict</h1>
          <p>
            The interface could not start. Reload to fetch the current build.
          </p>
          <p>
            If the problem persists, check that the frontend server is running
            and reload the page.
          </p>
          <button type="button" onClick={() => window.location.reload()}>
            Reload interface
          </button>
        </main>
      );
    return this.props.children;
  }
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <InterfaceBoundary>
      <App />
    </InterfaceBoundary>
  </StrictMode>,
);
