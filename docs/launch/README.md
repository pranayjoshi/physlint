# Public-alpha launch checklist

Nothing in this directory publishes externally. Complete the account and community actions manually after the repository state and artifacts are reviewed.

## Release gate

- [ ] All intended changes are reviewed and committed on a release branch.
- [ ] `pytest`, Ruff, strict mypy, source build, wheel build, and isolated wheel smoke test pass.
- [ ] `python -m validation.harness` passes every pinned clean source and corruption recipe.
- [ ] Committed reports contain no machine-local paths, secrets, images, or complete samples.
- [ ] `manifest.yaml`, `summary.json`, `summary.csv`, report checksums, and the narrative report agree.
- [ ] README claims remain scoped to LeRobot v3 and the pinned evidence.
- [ ] Package name `physlint` is confirmed on TestPyPI/PyPI before announcing its install command.

## GitHub setup

- [ ] Make the repository public and confirm LICENSE, SECURITY, CONTRIBUTING, issue templates, and roadmap render correctly.
- [ ] Enable GitHub Discussions.
- [ ] Create a discussion titled “Which Physlint adapter should be next?” with MCAP/ROS 2, Robomimic, RLDS/TFDS, and another-format options.
- [ ] Create an issue from `docs/design/mcap-ros.md` and label it `adapter`, `design-partner`, and `help-wanted`.
- [ ] Configure a protected GitHub environment named `pypi` with a required reviewer.
- [ ] Add `docs/assets/launch/validation-summary.png` as the repository social preview; keep the SVG as its editable source.
- [ ] Confirm CI passes on Python 3.11, 3.12, and 3.13.

## PyPI setup

- [ ] Enable two-factor authentication on the PyPI owner account.
- [ ] Configure a PyPI Trusted Publisher for owner `pranayjoshi`, repository `physlint`, workflow `publish.yml`, environment `pypi`.
- [ ] Configure the equivalent TestPyPI publisher for workflow `publish-testpypi.yml` and environment `testpypi`; run it before the production release.
- [ ] Create and publish GitHub release/tag `v0.1.0a1`; do not upload with a long-lived API token.
- [ ] Verify the published wheel and source distribution hashes and project links.
- [ ] Test in a new environment: `pipx run --spec 'physlint[video]==0.1.0a1' physlint --version`.
- [ ] Test one public dataset from the published artifact, not the editable checkout.

## Launch sequence

1. Publish the GitHub release and PyPI artifact.
2. Update installation text if the final package name differs.
3. Publish the technical validation note and repository link.
4. Share a feedback-oriented message in LeRobot Discord and the Hugging Face forum.
5. Publish LinkedIn and X posts using the same measured claims.
6. Submit Show HN only after anonymous users can install and run the tool without signup.
7. Share with ROS/MCAP communities as a design-partner request, clearly stating that MCAP is planned.
8. Contact the four tested dataset publishers privately with the report and attribution.

## First two-week success criteria

- 10 independently owned datasets tested
- Three new robot embodiments
- Every reported finding classified as true positive, false positive, or inconclusive
- Three maintainers willing to trial CI integration
- Two usable MCAP design-partner recordings or schemas
- One external rule, fixture, documentation, or adapter contribution

Record evidence in GitHub issues or a public launch retrospective. Do not substitute stars or impressions for defect and adoption evidence.

See [capture-assets.md](capture-assets.md) for exact recording steps and [post-templates.md](post-templates.md) for channel-specific copy.
