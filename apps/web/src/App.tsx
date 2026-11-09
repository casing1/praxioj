import { useEffect } from "react";
import { useRoute } from "./navigation";
import { ProblemList } from "./pages/ProblemList";
import { ProblemDetail } from "./pages/ProblemDetail";
import { Workspace } from "./pages/Workspace";
import { Evaluation } from "./pages/Evaluation";
import { Badge, Spark } from "./components/ui";

export function App() {
  const route = useRoute();
  const routeName =
    route.page === "session"
      ? "AI workspace"
      : route.page === "evaluation"
        ? "Evaluation result"
        : route.page === "problem"
          ? "Problem overview"
          : "Problem library";
  useEffect(() => {
    document.title = `${routeName} · PraxiOJ`;
    document.getElementById("main-content")?.focus({ preventScroll: true });
  }, [routeName]);
  return (
    <div className="app-shell">
      <a
        className="skip-link"
        href="#main-content"
        onClick={(event) => {
          event.preventDefault();
          document.getElementById("main-content")?.focus();
        }}
      >
        Skip to content
      </a>
      <aside className="sidebar">
        <a className="brand" href="#/" aria-label="PraxiOJ home">
          <span className="brand-mark">
            P<span />
          </span>
          <span>
            Praxi<span className="brand-light">OJ</span>
          </span>
        </a>
        <div className="sidebar-section-label">WORKBENCH</div>
        <nav aria-label="Main navigation">
          <a
            className={`sidebar-link ${route.page === "problems" || route.page === "problem" ? "selected" : ""}`}
            href="#/"
            aria-current={route.page === "problems" ? "page" : undefined}
          >
            <span className="library-icon" aria-hidden="true">
              ▦
            </span>
            Problem library
            <ArrowSmall />
          </a>
        </nav>
        <div className="sidebar-bottom">
          <span className="sidebar-symbol">
            <Spark />
          </span>
          <h2>People. AI. Possibility.</h2>
          <p>An open-source framework for evaluating human–AI collaboration.</p>
          <div className="sidebar-version">
            <span className="status-dot" /> AI Workspace · Milestone 2
          </div>
        </div>
      </aside>
      <div className="app-body">
        <header className="topbar">
          <div className="breadcrumb">
            <span>Practice lab</span>
            <span aria-hidden="true">/</span>
            <strong>{routeName}</strong>
          </div>
          <Badge tone="local">
            <span className="status-dot" />
            Local development
          </Badge>
        </header>
        <main
          id="main-content"
          aria-label={routeName}
          className={`main-content ${route.page === "session" ? "workspace-main" : ""}`}
          tabIndex={-1}
        >
          {route.page === "problems" ? (
            <ProblemList />
          ) : route.page === "problem" ? (
            <ProblemDetail
              key={`${route.id}/${route.version}`}
              id={route.id}
              version={route.version}
            />
          ) : route.page === "session" ? (
            <Workspace key={route.id} id={route.id} />
          ) : route.page === "evaluation" ? (
            <Evaluation key={route.id} id={route.id} />
          ) : (
            <div className="empty-state">
              <h1>Page not found</h1>
              <a href="#/" className="button primary">
                Back to problem library
              </a>
            </div>
          )}
        </main>
        <footer className="footer">
          <span>PraxiOJ · AI-Assisted Online Judge Framework</span>
          <span>Independent hobby project · Browser-local identity</span>
          <span>
            <a href="/LICENSE.txt" target="_blank" rel="noopener noreferrer">Apache-2.0</a>
            {" · "}
            <a href="/NOTICE.txt" target="_blank" rel="noopener noreferrer">Notice</a>
            {" · "}
            <a href="/THIRD_PARTY_NOTICES.txt" target="_blank" rel="noopener noreferrer">Third-party licenses</a>
          </span>
        </footer>
      </div>
    </div>
  );
}
function ArrowSmall() {
  return (
    <span className="nav-arrow" aria-hidden="true">
      ↗
    </span>
  );
}
