import type { Metadata } from "next";
import { ComparisonTable, type Comparison } from "./ComparisonTable";
import { ObservatoryTable, type Observation } from "./ObservatoryTable";
import catalog from "../data/observations.json";
import comparisonsCatalog from "../data/comparisons.json";

export const metadata: Metadata = {
  title: "Physlint Observatory — robot data health",
  description: "Reproducible validation evidence for LeRobot, MCAP, and ROS 2 recordings.",
  other: { "codex-preview": "development" },
};

const repo = "https://github.com/pranayjoshi/physlint";
const reportRoot = `${repo}/blob/master/validation/reports`;
const observations: Observation[] = catalog.observations.map((item) => ({
  ...item,
  profile: item.profile as Observation["profile"],
  provenance: item.provenance as Observation["provenance"],
  status: item.status as Observation["status"],
  sourceUrl: item.sourceUrl ?? undefined,
  reportUrl: `${reportRoot}/${item.reportPath}`,
}));
const comparisons: Comparison[] = comparisonsCatalog.comparisons.map((item) => ({
  ...item,
  status: item.status as Comparison["status"],
  baselineReportUrl: `${reportRoot}/${item.baselineReportPath}`,
  candidateReportUrl: `${reportRoot}/${item.candidateReportPath}`,
}));
const ruleRuns = observations.reduce((total, item) => total + item.checks, 0);
const surveyRows = observations.filter((item) => item.provenance === "Survey").length;

export default function Home() {
  return (
    <main>
      <nav className="nav shell">
        <a className="brand" href="#top" aria-label="Physlint Observatory home"><span className="brand-mark">P/</span><span>Observatory <small>by Physlint</small></span></a>
        <div className="nav-links"><a href="#method">Method</a><a href="#regressions">Regressions</a><a href="https://pypi.org/project/physlint/">PyPI</a><a className="github" href={repo}>GitHub ↗</a></div>
      </nav>

      <section className="hero shell" id="top">
        <div className="hero-copy">
          <p className="eyebrow">Open validation evidence · v0.3.1</p>
          <h1>Know your robot data<br />before it trains your model.</h1>
          <p className="lede">A transparent health index for robotics datasets and recordings. Every outcome links back to deterministic Physlint rules—never a mystery score.</p>
          <div className="hero-actions"><a className="button primary" href="#index">Explore evidence ↓</a><a className="button secondary" href={`${repo}#quickstart`}>Run it locally ↗</a></div>
        </div>
        <div className="hero-orbit" aria-hidden="true"><span className="orbit orbit-one"/><span className="orbit orbit-two"/><span className="core">P/</span><span className="signal signal-a"/><span className="signal signal-b"/><span className="signal signal-c"/></div>
        <div className="summary" aria-label="Validation summary">
          <div><strong>{observations.length}</strong><span>observations</span></div><div><strong>{comparisons.length}</strong><span>regression cases</span></div>
          <div><strong>{ruleRuns}</strong><span>rule runs</span></div><div><strong>{surveyRows || "7,047"}</strong><span>{surveyRows ? "survey rows" : "real ROS messages"}</span></div>
        </div>
      </section>

      <section className="index shell" id="index" aria-labelledby="index-title">
        <div className="section-heading">
          <div><p className="eyebrow">Evidence index · 30 Aug 2026</p><h2 id="index-title">Robot data health, in public.</h2></div>
          <p>Release-gate rows are Public or Controlled. Survey rows are stratified compatibility observations and are not a Hub quality score. “Passed” means the applicable checks found no configured blocking issues.</p>
        </div>
        <ObservatoryTable observations={observations} />
      </section>

      <section className="index shell" id="regressions" aria-labelledby="regression-title">
        <div className="section-heading">
          <div><p className="eyebrow">Dataset intelligence</p><h2 id="regression-title">Regressions, not a leaderboard.</h2></div>
          <p>physlint compare diffs fingerprints between a clean snapshot and a later candidate. New blocking findings are regressions; coverage lists what changed without inventing a score.</p>
        </div>
        <ComparisonTable comparisons={comparisons} />
      </section>

      <section className="workflows shell" id="workflows" aria-labelledby="workflow-title">
        <div className="section-heading">
          <div><p className="eyebrow">Data-engineer workflow</p><h2 id="workflow-title">A quality contract that can live in CI.</h2></div>
        </div>
        <div className="workflow-grid">
          <article><h3>compare</h3><p>Diff two dataset versions or JSON reports. Exit 1 only on new blocking findings.</p><code>physlint compare before/ after/</code></article>
          <article><h3>baseline</h3><p>Accept a known fingerprint with author, reason, and optional expiry. New instances of the same rule still fail.</p><code>physlint baseline . --author ada --reason known</code></article>
          <article><h3>CI reports</h3><p>JSON plus JUnit, SARIF, and a local HTML file. No images or raw samples are embedded.</p><code>--junit-output --sarif-output --html-output</code></article>
          <article><h3>plugins</h3><p>Load a file or entry-point rule. Task-specific idle detection stays out of the default contract.</p><code>plugins: [idle_prefix.py:IdlePrefixRule]</code></article>
        </div>
      </section>

      <section className="method" id="method">
        <div className="shell">
          <div className="method-title"><p className="eyebrow light">How to read the index</p><h2>Evidence over<br />leaderboard theater.</h2></div>
          <div className="principles">
            <article><span>01</span><h3>Profile-aware</h3><p>LeRobot datasets, generic MCAP recordings, and ROS 2 topics are judged by separate, explicit contracts.</p></article>
            <article><span>02</span><h3>Reproducible</h3><p>Sources are revision-pinned. Reports preserve configuration digests, rule versions, and SHA-256 fingerprints.</p></article>
            <article><span>03</span><h3>Privacy-safe</h3><p>Only sanitized evidence is published. Raw robot recordings, images, and full samples stay with their owners.</p></article>
            <article><span>04</span><h3>Open to challenge</h3><p>Every finding identifies its rule and evidence. Disagree? Re-run it, inspect the report, or improve the rule.</p></article>
          </div>
        </div>
      </section>

      <section className="cta shell">
        <p className="eyebrow">Bring your own recording</p><h2>Make your data quality<br />a visible engineering practice.</h2>
        <div><code>pip install physlint</code><a className="button primary" href={`${repo}#quickstart`}>Get started ↗</a></div>
      </section>
      <footer className="footer shell"><span>Physlint Observatory · Open source under MIT</span><span>Reports are evidence, not safety certification.</span></footer>
    </main>
  );
}
