"use client";

import { useMemo, useState } from "react";

export type Observation = {
  id: string;
  name: string;
  source: string;
  robot: string;
  profile: "LeRobot" | "MCAP" | "ROS 2";
  provenance: "Public" | "Controlled";
  scale: string;
  checks: number;
  findings: number;
  status: "Passed" | "Issues found";
  reportUrl: string;
  sourceUrl?: string;
  revision?: string;
};

const filters = ["All", "LeRobot", "MCAP", "ROS 2"] as const;

export function ObservatoryTable({ observations }: { observations: Observation[] }) {
  const [filter, setFilter] = useState<(typeof filters)[number]>("All");
  const [query, setQuery] = useState("");
  const filtered = useMemo(() => observations.filter((item) => {
    const inProfile = filter === "All" || item.profile === filter;
    const text = `${item.name} ${item.source} ${item.robot}`.toLowerCase();
    return inProfile && text.includes(query.trim().toLowerCase());
  }), [filter, observations, query]);

  return (
    <>
      <div className="toolbar">
        <div className="filters" aria-label="Filter by profile">
          {filters.map((item) => (
            <button className={filter === item ? "filter active" : "filter"} key={item} onClick={() => setFilter(item)} type="button">
              {item}
            </button>
          ))}
        </div>
        <label className="search">
          <span className="sr-only">Search observations</span>
          <span aria-hidden="true">⌕</span>
          <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search robot or source" />
        </label>
      </div>
      <div className="table-wrap">
        <table>
          <thead><tr><th>#</th><th>Dataset / recording</th><th>Profile</th><th>Scale</th><th>Checks</th><th>Findings</th><th>Outcome</th><th>Evidence</th></tr></thead>
          <tbody>{filtered.map((item, index) => (
            <tr key={item.id}>
              <td className="rank">{String(index + 1).padStart(2, "0")}</td>
              <td>
                {item.sourceUrl ? <a className="recording-name" href={item.sourceUrl}>{item.name} ↗</a> : <span className="recording-name">{item.name}</span>}
                <span className="recording-meta">{item.robot} · {item.provenance} evidence</span>
              </td>
              <td><span className={`profile profile-${item.profile.toLowerCase().replace(" ", "-")}`}>{item.profile}</span></td>
              <td>{item.scale}</td><td>{item.checks}</td><td>{item.findings}</td>
              <td><span className={item.status === "Passed" ? "status pass" : "status issue"}>{item.status}</span></td>
              <td><a className="evidence" href={item.reportUrl} aria-label={`Open evidence for ${item.name}`}>Report ↗</a></td>
            </tr>
          ))}</tbody>
        </table>
        {filtered.length === 0 && <p className="empty">No observations match this filter.</p>}
      </div>
      <p className="index-note">Order shows the current evidence catalog—not a universal quality ranking. Different profiles run different contracts.</p>
    </>
  );
}
