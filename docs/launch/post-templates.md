# Launch post templates

Replace `[LINK]` only after the repository and package are public. Recheck every number against the committed summary before posting.

For the 18-second clip, use the [marketing plan](marketing-plan.md). Version 0.4.0 includes the demo, direct Hub sources, native LeRobot v2 support, doctor, and JSON interfaces. Link the README's version-pinned installation command.

## Core positioning

**Headline:** Physlint catches physical-AI data integrity defects before training.

**Scope sentence:** Physlint validates LeRobot v3 datasets, generic MCAP containers, and ROS 2-over-MCAP recordings; Robomimic HDF5 and RLDS remain roadmap formats.

Do not use “supports all robot data,” “production ready,” “guarantees dataset quality,” or “prevents bad policies.”

## LinkedIn

Bad robot data is expensive to discover after training starts.

I built Physlint, an open-source, local-first integrity validator for physical-AI recordings and robot-learning datasets. It validates LeRobot v3 datasets, generic MCAP containers, and ROS 2-over-MCAP recordings. Its 32 deterministic rules cover schemas, episode boundaries, timestamps, numeric streams, video decoding, frozen cameras, black frames, container/index health, and ROS 2 topic semantics.

For the release gate I tested four immutable public repositories from four producers: 74 episodes and 31,258 frames. All four clean snapshots passed with no findings or rule errors, and Physlint detected 3/3 controlled corruptions. The manifest, corruption recipes, sanitized JSON reports, and checksums are public and reproducible.

The CLI now accepts revision-pinned Hugging Face sources, emits versioned machine-readable reports, runs safely around dataset-local configuration, and ships as a reusable GitHub Action. I am looking for maintainers who can test another dataset or recording and contributors interested in Robomimic HDF5, RLDS, or another explicit adapter.

[LINK]

## X thread

1. Bad robot data is expensive to discover after training begins. I built Physlint: a local-first integrity validator for physical-AI data. [LINK]
2. Physlint has 32 deterministic, format-aware rules for LeRobot v3, generic MCAP, and ROS 2 over MCAP—with JSON, JUnit, SARIF, and HTML reports for CI and coding agents.
3. Reproducible release gate: 4 public snapshots, 74 episodes, 31,258 frames, 4/4 clean passes, and 3/3 controlled corruptions detected. Manifest, recipes, reports, and hashes are committed.
4. Run the built-in demo, check a revision-pinned Hugging Face dataset, or add the reusable GitHub Action. Robomimic HDF5 and RLDS remain explicit roadmap formats.

## LeRobot Discord or Hugging Face forum

I have released Physlint, a local-first integrity checker for LeRobot v3 datasets and robot recordings. I validated its LeRobot contract against four pinned public repositories and three reproducible corruptions; all evidence is committed here: [LINK].

I am specifically looking for false positives and unsupported-but-valid v3 layouts. If you maintain a public dataset, please share an immutable revision and the expected behavior. This is an alpha feedback request, not a claim that passing guarantees training quality.

## ROS/MCAP community

Physlint now includes generic MCAP integrity checks and an optional ROS 2 semantic profile. The implementation has pinned public and deterministic evidence, while the four-snapshot LeRobot gate remains a separate claim.

The generic layer checks record and CRC readability, summary/index coverage, channel/schema coherence, timestamp order, duplicates, and sequence continuity. The ROS 2 profile adds portable CDR decoding, required-topic checks, cadence gaps, header/log skew, known-message invariants, and TF parent consistency.

I am looking for small public recordings and real failure modes to broaden the evidence without overstating format coverage: [LINK TO ADAPTER ISSUE].

## Show HN

**Title:** Show HN: Physlint – a local-first linter for robot-learning datasets

**First comment:** Explain why the project exists, give the one-command demo and a revision-pinned public dataset command, link the reproducible validation directories, state the exact implemented adapters and boundaries, and remain available to answer technical questions. Do not ask anyone to upvote.

## Direct maintainer outreach

Subject: Reproducible Physlint result for `[DATASET@REVISION]`

I used your public dataset as one of four immutable inputs for the Physlint alpha release gate. The unmodified pinned revision passed the applicable integrity rules with no findings or rule errors. The sanitized report and exact manifest entry are here: [LINK].

Thank you for making the dataset public. If you are open to it, I would value your review of the format assumptions and whether a Physlint check would be useful in your collection or publishing workflow. I will correct attribution or remove the dataset from marketing material if you prefer.
