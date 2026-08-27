# Physlint Observatory

The public evidence index for Physlint. It presents revision-pinned LeRobot, MCAP, and ROS 2 validation results without collapsing unlike quality contracts into a universal score.

## Local development

Requires Node.js 22.13 or newer.

```bash
npm install
npm run dev
npm test
```

The published reports remain the source of truth under `../validation/reports/`. The site contains a publication-friendly catalog derived from those sanitized reports; it never embeds raw recordings or complete samples.
