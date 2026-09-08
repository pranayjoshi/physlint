import type { Metadata } from "next";
import { ObservatoryTable, type Observation } from "./ObservatoryTable";
import catalog from "../data/observations.json";

export const metadata: Metadata = {
  title: "Physlint Evidence Atlas",
  description: "Reproducible evidence for robot dataset and recording health.",
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
    copy: "A deterministic edit reproduced clock reversal, an unexpected sampling interval, and an excessive gap, without changing the original source.",
    rule: "temporal.monotonic",
    href: `${reportRoot}/real-data-2026-08-24/corruption-reordered.json`,
  },
  {
    number: "03",
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
        <a className="brand" href="#top" aria-label="Physlint Evidence Atlas home"><span className="brand-mark">P/</span><span>Evidence Atlas <small>by Physlint</small></span></a>
        <div className="nav-links"><a href="#index">Atlas</a><a href="#stories">Findings</a><a href="#contribute">Contribute</a><a className="github" href={repo}>GitHub ↗</a></div>
      </nav>

      <section className="hero shell" id="top">
        <div className="hero-copy">
          <p className="eyebrow">Open, reproducible evidence</p>
          <h1>Know your robot data<br />before training.</h1>
          <p className="lede">Explore pinned checks of public LeRobot, MCAP, and ROS 2 data. Every result links to the exact report.</p>
          <div className="hero-actions"><a className="button primary" href="#index">Explore the atlas ↓</a><a className="button secondary" href="#contribute">Submit evidence ↗</a></div>
        </div>
        <div className="hero-orbit" aria-hidden="true"><span className="orbit orbit-one"/><span className="orbit orbit-two"/><span className="core">P/</span><span className="signal signal-a"/><span className="signal signal-b"/><span className="signal signal-c"/></div>
        <div className="summary" aria-label="Validation summary">
          <div><strong>{observations.length}</strong><span>published observations</span></div>
          <div><strong>{ruleRuns.toLocaleString("en-US")}</strong><span>applicable checks</span></div>
          <div><strong>{profileCount}</strong><span>quality profiles</span></div>
        </div>
      </section>

      <section className="index shell" id="index" aria-labelledby="index-title">
        <div className="section-heading">
          <div><p className="eyebrow">Evidence atlas</p><h2 id="index-title">Explore every check.</h2></div>
          <p>Filter by format, inspect the outcome, and open the reproducible report.</p>
        </div>
        <ObservatoryTable observations={observations} />
      </section>

      <section className="stories shell" id="stories" aria-labelledby="stories-title">
        <div className="section-heading">
          <div><p className="eyebrow">Selected findings</p><h2 id="stories-title">Concrete defects. Exact evidence.</h2></div>
          <p>Each finding links to its rule and sanitized report.</p>
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

      <section className="contribute shell" id="contribute" aria-labelledby="contribute-title">
        <div className="contribute-copy">
          <p className="eyebrow">Contribute</p>
          <h2 id="contribute-title">Add your robot data.</h2>
          <p>Share a pinned public dataset or recording. Physlint keeps the source untouched and publishes only sanitized evidence.</p>
          <div className="hero-actions"><a className="button primary" href={`${repo}/issues/new?template=evidence-submission.yml`}>Submit evidence ↗</a><a className="button secondary" href={`${repo}/discussions`}>Discuss ↗</a></div>
        </div>
        <ol className="contribute-steps">
          <li><span>01</span><div><h3>Share a revision</h3><p>Link a public source that can be pinned.</p></div></li>
          <li><span>02</span><div><h3>Add context</h3><p>Name the robot, format, and expected behavior.</p></div></li>
          <li><span>03</span><div><h3>Get evidence</h3><p>Receive a scoped, reproducible report.</p></div></li>
        </ol>
      </section>

      <section className="cta shell">
        <p className="eyebrow">Run it locally</p><h2>Check data before training.</h2>
        <div><code>pip install physlint</code><a className="button primary" href={`${repo}#quickstart`}>Run Physlint ↗</a></div>
      </section>
      <footer className="footer shell"><span>Physlint Community Evidence Atlas · Open source under MIT</span><span>Reports are scoped evidence, not safety certification.</span></footer>
    </main>
  );
}
