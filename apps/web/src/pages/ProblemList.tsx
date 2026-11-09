import { useResource } from "../api";
import type { Problem } from "../types";
import { problemHref } from "../navigation";
import {
  Arrow,
  Badge,
  ErrorNotice,
  Loading,
  PageHeading,
  Spark,
} from "../components/ui";

export function ProblemList() {
  const {
    data: problems,
    loading,
    error,
    retry,
  } = useResource<Problem[]>("/problems");
  return (
    <>
      <PageHeading
        eyebrow="THE PRACTICE LAB"
        title="A place to think. A partner to build."
        description="Explore a problem, work with AI, and make your process count."
      />
      <section className="intro-banner" aria-label="How PraxiOJ works">
        <div className="intro-copy">
          <Badge tone="dark">HUMAN + AI</Badge>
          <h2>
            The way you solve
            <br />
            is part of the solution.
          </h2>
          <p>
            Bring your judgment. Ask better questions. Turn a conversation into
            something worth submitting.
          </p>
          <a
            href="#problem-list"
            className="text-link"
            onClick={(event) => {
              event.preventDefault();
              document
                .getElementById("problem-list")
                ?.scrollIntoView({ behavior: "smooth" });
            }}
          >
            Find your next problem <Arrow />
          </a>
        </div>
        <div className="process-illustration" aria-hidden="true">
          <div className="orbit orbit-one" />
          <div className="orbit orbit-two" />
          <div className="process-node human-node">
            <span>01</span>You
          </div>
          <div className="process-node ai-node">
            <Spark />
            AI
          </div>
          <div className="process-node outcome-node">
            <span>↗</span>Outcome
          </div>
          <div className="process-center">+</div>
        </div>
      </section>
      <section className="library-section" id="problem-list">
        <div className="section-heading">
          <div>
            <h2>Problem library</h2>
            <p>Small challenges. Meaningful collaboration.</p>
          </div>
          {problems ? (
            <span className="count-label">
              {problems.length} {problems.length === 1 ? "problem" : "problems"}{" "}
              available
            </span>
          ) : null}
        </div>
        {loading ? (
          <Loading label="Loading problems…" />
        ) : error ? (
          <ErrorNotice message={error} retry={retry} />
        ) : problems?.length === 0 ? (
          <div className="empty-state">
            <h3>The library is ready for its first problem.</h3>
            <p>
              Register a problem package with the local CLI, then refresh the
              library.
            </p>
            <button className="button secondary" onClick={retry}>
              Refresh library
            </button>
          </div>
        ) : (
          <div className="problem-list">
            {problems?.map((problem, index) => (
              <a
                className="problem-card"
                href={problemHref(problem.id, problem.version)}
                key={`${problem.id}/${problem.version}`}
              >
                <span className="problem-number">
                  {String(index + 1).padStart(2, "0")}
                </span>
                <div className="problem-card-copy">
                  <div className="problem-tags">
                    <Badge>{problem.category}</Badge>
                    <span className="difficulty">{problem.difficulty}</span>
                  </div>
                  <h3>{problem.title}</h3>
                  <p>{problem.description}</p>
                  <div className="problem-card-meta">
                    <span>Text submission</span>
                    <span className="meta-divider">·</span>
                    <span>
                      {problem.evaluation.criteria.length} evaluation criteria
                    </span>
                    <span className="meta-divider">·</span>
                    <span>v{problem.version}</span>
                  </div>
                </div>
                <span className="problem-card-arrow">
                  <Arrow />
                </span>
              </a>
            ))}
          </div>
        )}
      </section>
      <section className="journey" aria-label="Your workflow">
        {[
          {
            number: "01",
            title: "Understand the problem",
            text: "Read the brief, resources, and evaluation criteria.",
          },
          {
            number: "02",
            title: "Think alongside AI",
            text: "Use the built-in conversation to develop your approach.",
          },
          {
            number: "03",
            title: "Submit and reflect",
            text: "Review your result and the record of your work.",
          },
        ].map((step) => (
          <div className="journey-step" key={step.number}>
            <span>{step.number}</span>
            <div>
              <h3>{step.title}</h3>
              <p>{step.text}</p>
            </div>
          </div>
        ))}
      </section>
    </>
  );
}
