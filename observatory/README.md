# Physlint Observatory

The public evidence index for Physlint. It presents revision-pinned LeRobot, MCAP, and ROS 2 validation results, plus fingerprint-level regression diffs, without collapsing unlike quality contracts into a universal score.

Release-gate rows stay Public or Controlled. Compatibility-survey rows are tagged Survey and are not a Hugging Face quality score. See `docs/validation/compatibility-survey.md`.

## Local development

Requires Node.js 22.13 or newer.

```bash
npm install
npm run dev
npm test
```

Regenerate the catalogs after validation reports change:

```bash
python -m validation.build_observatory
```

The published reports remain the source of truth under `../validation/reports/`. The site contains a publication-friendly catalog derived from those sanitized reports; it never embeds raw recordings or complete samples.
