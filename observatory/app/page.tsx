import type { Metadata } from "next";
import { ObservatoryTable, type Observation } from "./ObservatoryTable";
import catalog from "../data/observations.json";

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

export default function Home() {
  return (
    <main>
      <nav className="nav shell">
        <a className="brand" href="#top" aria-label="Physlint Observatory home"><span className="brand-mark">P/</span><span>Observatory <small>by Physlint</small></span></a>
        <div className="nav-links"><a href="#method">Method</a><a href="https://pypi.org/project/physlint/">PyPI</a><a className="github" href={repo}>GitHub ↗</a></div>
      </nav>

      <section className="hero shell" id="top">
        <div className="hero-copy">
          <p className="eyebrow">Open validation evidence · v0.2 preview</p>
          <h1>Know your robot data<br />before it trains your model.</h1>
          <p className="lede">A transparent health index for robotics datasets and recordings. Every outcome links back to deterministic Physlint rules—never a mystery score.</p>
          <div className="hero-actions"><a className="button primary" href="#index">Explore evidence ↓</a><a className="button secondary" href={`${repo}#quickstart`}>Run it locally ↗</a></div>
        </div>
        <div className="hero-orbit" aria-hidden="true"><span className="orbit orbit-one"/><span className="orbit orbit-two"/><span className="core">P/</span><span className="signal signal-a"/><span className="signal signal-b"/><span className="signal signal-c"/></div>
        <div className="summary" aria-label="Validation summary">
          <div><strong>8</strong><span>observations</span></div><div><strong>3</strong><span>quality profiles</span></div>
          <div><strong>97</strong><span>rule runs</span></div><div><strong>7,047</strong><span>real ROS messages</span></div>
        </div>
      </section>

      <section className="index shell" id="index" aria-labelledby="index-title">
        <div className="section-heading">
          <div><p className="eyebrow">Evidence index · 27 Aug 2026</p><h2 id="index-title">Robot data health, in public.</h2></div>
          <p>Filter verified datasets and diagnostic cases by contract. “Passed” means the applicable checks found no configured blocking issues.</p>
        </div>
        <ObservatoryTable observations={observations} />
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
