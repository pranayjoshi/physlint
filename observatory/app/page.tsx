import type { Metadata } from "next";
import { ObservatoryTable, type Observation } from "./ObservatoryTable";
import catalog from "../data/observations.json";

export const metadata: Metadata = {
  title: "Community Evidence Atlas — robot data health",
  description: "A community map of reproducible health evidence for LeRobot, MCAP, and ROS 2 datasets and recordings.",
  other: { "codex-preview": "development" },
};

const repo = "https://github.com/pranayjoshi/physlint";
const reportRoot = `${repo}/blob/master/validation/reports`;
const observations: Observation[] = catalog.observations.map((item) => ({
  ...item,
  profile: item.profile as Observation["profile"],
  provenance: item.provenance as Observation["provenance"],
  status: item.status as Observation["status"],
  note: typeof item.note === "string" ? item.note : undefined,
  sourceUrl: item.sourceUrl ?? undefined,
  reportUrl: `${reportRoot}/${item.reportPath}`,
}));
const ruleRuns = observations.reduce((total, item) => total + item.checks, 0);
const rosMessages = observations.find((item) => item.id === "robotis-arx5-button")?.scale.split(" ")[0] ?? "7,047";
const surveyCount = observations.filter((item) => item.provenance === "Survey").length;
const profileCount = new Set(observations.map((item) => item.profile)).size;

const stories = [
  {
    number: "01",
    label: "Confirmed public defect",
    title: "Metadata pointed to shards that were never published.",
    copy: "The Reachy 2 Head sample declared Parquet files that were absent from its public revision. The dataset could be discovered, but not reliably consumed.",
    rule: "manifest.required_files",
    href: `${reportRoot}/lerobot-survey-2026-08-30/check-reachy-head.json`,
  },
  {
    number: "02",
    label: "Controlled evidence",
    title: "One reordered timestamp exposed three timing failures.",
    copy: "A deterministic edit reproduced clock reversal, an unexpected sampling interval, and an excessive gap—without changing the original source.",
    rule: "temporal.monotonic",
    href: `${reportRoot}/real-data-2026-08-24/corruption-reordered.json`,
  },
  {
    number: "03",
    label: "Controlled evidence",
    title: "A single non-finite value was isolated before training.",
    copy: "One injected NaN in robot state was traced to its episode, sample, stream, and dimension with a concrete remediation path.",
    rule: "numeric.finite_values",
    href: `${reportRoot}/real-data-2026-08-24/corruption-nan.json`,
  },
  {
    number: "04",
    label: "ROS 2 evidence",
    title: "A topic gap and malformed JointState were separated cleanly.",
    copy: "The recording showed both a cadence break and a position/name dimension mismatch, each reported under the rule that owns it.",
    rule: "ros2.semantic_consistency",
    href: `${reportRoot}/mcap-ros2-2026-08-26/ros2-joint-state-corrupt.json`,
  },
];

export default function Home() {
  return (
    <main>
      <nav className="nav shell">
        <a className="brand" href="#top" aria-label="Physlint Community Evidence Atlas home"><span className="brand-mark">P/</span><span>Evidence Atlas <small>by Physlint</small></span></a>
        <div className="nav-links"><a href="#index">Atlas</a><a href="#stories">Findings</a><a href="#contribute">Contribute</a><a href="#method">Method</a><a className="github" href={repo}>GitHub ↗</a></div>
      </nav>

      <section className="hero shell" id="top">
        <div className="hero-copy">
          <p className="eyebrow">Community release · 06 Sep 2026</p>
          <h1>The public map of<br />robot data health.</h1>
          <p className="lede">An open atlas of robotics datasets, recordings, and the integrity evidence behind them. See what was checked, what needs review, and how to add your own data—without a mystery score.</p>
          <div className="hero-actions"><a className="button primary" href="#index">Explore the atlas ↓</a><a className="button secondary" href="#contribute">Put your data on the map ↗</a></div>
        </div>
        <div className="hero-orbit" aria-hidden="true"><span className="orbit orbit-one"/><span className="orbit orbit-two"/><span className="core">P/</span><span className="signal signal-a"/><span className="signal signal-b"/><span className="signal signal-c"/></div>
        <div className="summary" aria-label="Validation summary">
          <div><strong>{observations.length}</strong><span>published observations</span></div>
          <div><strong>{surveyCount}</strong><span>community survey records</span></div>
          <div><strong>{ruleRuns.toLocaleString("en-US")}</strong><span>applicable checks</span></div>
          <div><strong>{profileCount}</strong><span>quality profiles</span></div>
        </div>
      </section>

      <section className="findings shell" aria-labelledby="findings-title">
        <div className="section-heading">
          <div><p className="eyebrow">What the evidence says today</p><h2 id="findings-title">A snapshot, not a verdict.</h2></div>
          <p>The atlas separates release-gate evidence, community survey observations, and controlled defects so each result stays honest about what it proves.</p>
        </div>
        <div className="finding-grid">
          <article><strong>6</strong><h3>Public sources checked</h3><p>Five healthy datasets or recordings passed their applicable contracts. One MCAP conformance case reproduced its known timestamp defects.</p></article>
          <article><strong>15</strong><h3>Survey snapshots mapped</h3><p>Ten LeRobot v3 datasets were checked in depth. Five older v2 or v2.1 datasets were deliberately rejected rather than guessed through.</p></article>
          <article><strong>{Number(rosMessages).toLocaleString("en-US")}</strong><h3>Real ROS messages decoded</h3><p>A public ARX X5 episode passed its configured ROS 2 contract, showing the atlas extends beyond training-dataset folders.</p></article>
        </div>
      </section>

      <section className="index shell" id="index" aria-labelledby="index-title">
        <div className="section-heading">
          <div><p className="eyebrow">Community evidence atlas</p><h2 id="index-title">Explore every observation.</h2></div>
          <p>Release-gate rows (Public or Controlled) are the scoped claim. Survey rows are a stratified Hub sample, including classified false positives and fail-closed v2 screens. “Passed” means the applicable checks found no configured blocking issues.</p>
        </div>
        <ObservatoryTable observations={observations} />
      </section>

      <section className="stories shell" id="stories" aria-labelledby="stories-title">
        <div className="section-heading">
          <div><p className="eyebrow">Evidence, made tangible</p><h2 id="stories-title">What a real defect looks like.</h2></div>
          <p>Each story links to a sanitized report with the exact rule, evidence, impact, and suggested remediation.</p>
        </div>
        <div className="story-grid">
          {stories.map((story) => (
            <article key={story.number}>
              <div className="story-meta"><span>{story.number}</span><span>{story.label}</span></div>
              <h3>{story.title}</h3>
              <p>{story.copy}</p>
              <div className="story-footer"><code>{story.rule}</code><a href={story.href}>Read evidence ↗</a></div>
            </article>
          ))}
        </div>
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
            <article><span>01</span><h3>Profile-aware</h3><p>LeRobot, generic MCAP, and ROS 2 use separate contracts. Survey rows never collapse into the release-gate claim or a Hub quality score.</p></article>
            <article><span>02</span><h3>Reproducible</h3><p>Sources are revision-pinned. Reports preserve configuration digests, rule versions, and SHA-256 fingerprints.</p></article>
            <article><span>03</span><h3>Privacy-safe</h3><p>Only sanitized evidence is published. Raw robot recordings, images, and full samples stay with their owners.</p></article>
            <article><span>04</span><h3>Open to challenge</h3><p>Every finding identifies its rule and evidence. Disagree? Re-run it, inspect the report, or improve the rule.</p></article>
          </div>
        </div>
      </section>

      <section className="contribute shell" id="contribute" aria-labelledby="contribute-title">
        <div className="contribute-copy">
          <p className="eyebrow">Open call for evidence</p>
          <h2 id="contribute-title">Put your robot data<br />on the map.</h2>
          <p>Share an immutable public dataset or recording and what you expect it to demonstrate. Physlint will keep the source untouched, publish only sanitized evidence, and distinguish confirmed defects from findings that need human review.</p>
          <div className="hero-actions"><a className="button primary" href={`${repo}/issues/new?template=evidence-submission.yml`}>Submit public evidence ↗</a><a className="button secondary" href={`${repo}/discussions`}>Join the discussion ↗</a></div>
        </div>
        <ol className="contribute-steps">
          <li><span>01</span><div><h3>Share a public revision</h3><p>Link a dataset or recording that can be pinned and reproduced.</p></div></li>
          <li><span>02</span><div><h3>Tell us what matters</h3><p>Describe the robot, format, and any real failure mode the community should understand.</p></div></li>
          <li><span>03</span><div><h3>Get transparent evidence</h3><p>A published result names the checks, scope, provenance, and review status—never a universal score.</p></div></li>
        </ol>
      </section>

      <section className="cta shell">
        <p className="eyebrow">The atlas is open</p><h2>Make robot data quality<br />a shared public practice.</h2>
        <div><code>pip install physlint</code><a className="button primary" href={`${repo}#quickstart`}>Run Physlint ↗</a></div>
      </section>
      <footer className="footer shell"><span>Physlint Community Evidence Atlas · Open source under MIT</span><span>Reports are scoped evidence, not safety certification.</span></footer>
    </main>
  );
}
