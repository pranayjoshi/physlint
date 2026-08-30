"use client";

export type Comparison = {
  id: string;
  title: string;
  status: "unchanged" | "improved" | "regressed" | "changed";
  newFindings: number;
  resolvedFindings: number;
  persistentFindings: number;
  newRules: string[];
  baselineReportUrl: string;
  candidateReportUrl: string;
};

export function ComparisonTable({ comparisons }: { comparisons: Comparison[] }) {
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Case</th>
            <th>Outcome</th>
            <th>New</th>
            <th>Resolved</th>
            <th>Rules</th>
            <th>Evidence</th>
          </tr>
        </thead>
        <tbody>
          {comparisons.map((item) => (
            <tr key={item.id}>
              <td>
                <span className="recording-name">{item.title}</span>
                <span className="recording-meta">{item.id}</span>
              </td>
              <td>
                <span className={item.status === "regressed" ? "status issue" : "status pass"}>
                  {item.status}
                </span>
              </td>
              <td>{item.newFindings}</td>
              <td>{item.resolvedFindings}</td>
              <td>{item.newRules.join(", ") || "—"}</td>
              <td>
                <a className="evidence" href={item.baselineReportUrl}>Before ↗</a>
                {" · "}
                <a className="evidence" href={item.candidateReportUrl}>After ↗</a>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="index-note">A regression is a new blocking finding. Coverage drift is reported without a universal score.</p>
    </div>
  );
}
