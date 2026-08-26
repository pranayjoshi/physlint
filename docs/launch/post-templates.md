# Launch post templates

Replace `[LINK]` only after the repository and package are public. Recheck every number against the committed summary before posting.

## Core positioning

**Headline:** Physlint catches physical-AI data integrity defects before training.

**Scope sentence:** The public alpha ships with a tested LeRobot v3 adapter; MCAP/ROS 2 and Robomimic are planned, and design partners are welcome.

Do not use “supports all robot data,” “production ready,” “guarantees dataset quality,” or “prevents bad policies.”

## LinkedIn

Bad robot data is expensive to discover after training starts.

I built Physlint, an open-source, local-first integrity validator for physical-AI recordings and robot-learning datasets. The first public alpha supports LeRobot v3 and checks schemas, episode boundaries, timestamps, actions, observations, video decoding, frozen cameras, and black frames.

For the release gate I tested four immutable public repositories from four producers: 74 episodes and 31,258 frames. All four clean snapshots passed with no findings or rule errors, and Physlint detected 3/3 controlled corruptions. The manifest, corruption recipes, sanitized JSON reports, and checksums are public and reproducible.

The broader engine is format-extensible. MCAP/ROS 2 recording validation and Robomimic HDF5 are next—not features hidden behind the alpha label. I am looking for maintainers who can test another LeRobot dataset and ROS teams willing to share a small representative MCAP schema or recording.

[LINK]

## X thread

1. Bad robot data is expensive to discover after training begins. I built Physlint: a local-first integrity validator for physical-AI data. [LINK]
2. The public alpha supports LeRobot v3: schemas, boundaries, timestamps, numeric streams, video decode, frozen cameras, and black frames—with exact CI-safe evidence.
3. Reproducible release gate: 4 public snapshots, 74 episodes, 31,258 frames, 4/4 clean passes, and 3/3 controlled corruptions detected. Manifest, recipes, reports, and hashes are committed.
4. The vision is cross-format. MCAP/ROS 2 and Robomimic are next. Try it on a LeRobot dataset—or share a representative MCAP schema and help design the recording profile.

## LeRobot Discord or Hugging Face forum

I have released an early alpha of Physlint, a local-first LeRobot v3 integrity checker. I validated it against four pinned public repositories and three reproducible corruptions; all evidence is committed here: [LINK].

I am specifically looking for false positives and unsupported-but-valid v3 layouts. If you maintain a public dataset, please share an immutable revision and the expected behavior. This is an alpha feedback request, not a claim that passing guarantees training quality.

## ROS/MCAP community

I am designing the next Physlint adapter for MCAP/ROS 2 recording integrity. MCAP is not supported in the current alpha; LeRobot v3 is the implemented release gate.

The proposed first layer checks container/index/schema health, per-channel timing, rate gaps, clock skew, and image decoding without assuming training semantics. An optional profile would map topics to actions, state, cameras, and episode markers.

I am looking for small public recordings and real failure modes to prevent the profile from being designed around synthetic assumptions: [LINK TO DESIGN ISSUE].

## Show HN

**Title:** Show HN: Physlint – a local-first linter for robot-learning datasets

**First comment:** Explain why the project exists, give the one-command install and a public dataset command, link the reproducible validation directory, state that LeRobot v3 is the current adapter, and remain available to answer technical questions. Do not ask anyone to upvote.

## Direct maintainer outreach

Subject: Reproducible Physlint result for `[DATASET@REVISION]`

I used your public dataset as one of four immutable inputs for the Physlint alpha release gate. The unmodified pinned revision passed the applicable integrity rules with no findings or rule errors. The sanitized report and exact manifest entry are here: [LINK].

Thank you for making the dataset public. If you are open to it, I would value your review of the format assumptions and whether a Physlint check would be useful in your collection or publishing workflow. I will correct attribution or remove the dataset from marketing material if you prefer.
