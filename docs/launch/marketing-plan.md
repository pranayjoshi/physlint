# Physlint launch plan

Prepared October 22, 2026. Channel choices below are recommendations based on audience fit, not measured conversion rates.

## Positioning

Lead with: **Find broken robot data before training.** Show a concrete failure, its exact location, and the command someone can run on their own dataset.

The first audience is people collecting or publishing LeRobot v3 datasets. A second audience is engineers maintaining ROS 2 recordings and MCAP pipelines. CI maintainers and coding-agent users are a distribution path into those teams. Broad AI audiences are less likely to have a dataset ready to check.

Use the 18-second social clip as the opening demonstration. It shows a deliberately injected NaN in a synthetic dataset. The longer technical explanation belongs in the README and pinned evidence reports. Do not imply that this example was discovered in someone else's public dataset or that it proves better policy performance.

## Before announcing

For the 0.4.0 launch, install `physlint[all]==0.4.0` and run `physlint doctor` followed by `physlint demo`. Verify the published wheel in a clean environment before posting. The older 0.3.2 package does not include the demo; use the current version-pinned command from the README.

Use the repository README as the main destination for the launch. It has the installation and demo instructions. The evidence atlas at physlint.com supports technical due diligence, but a visitor should not need to understand the atlas to try the CLI.

## Where to start

| Priority | Channel | What to publish | Ask |
|---|---|---|---|
| 1 | [LeRobot Discord, linked by its maintainers](https://github.com/huggingface/lerobot#resources) | An 18-second clip and short explanation of a reproducible NaN finding in a LeRobot v3 dataset. Follow the server's current channel rules. | Ask five maintainers to run one dataset and report false positives or missing checks. |
| 2 | Dataset maintainers you already have evidence for | Prepare individual notes linking their exact revision and sanitized report. Use an existing contact route they provide. | Ask whether the finding interpretation is correct and whether they would trial CI. Obtain authorization before sending messages from this workspace. |
| 3 | [Open Robotics Discourse](https://discourse.openrobotics.org/) | A technical introduction focused on MCAP container checks and ROS 2 CDR/topic/timing checks. Pick the current appropriate project/community category after reading its rules. | Ask for one small reproducible recording and one real failure mode. |
| 4 | [Foxglove community](https://foxglove.dev/community) | Explain how validation fits before inspecting recordings in a visual tool. Include a container failure and a semantic failure as separate examples. | Ask MCAP users which failures should block recording ingestion. |
| 5 | Your LinkedIn and X accounts | Upload the 4:5 MP4 natively, add the README link, and describe the exact synthetic corruption. | Ask readers to run the demo or volunteer a dataset. |
| 6 | [Show HN](https://news.ycombinator.com/showhn.html) | Submit the runnable repository as “Show HN: Physlint, a local linter for robot datasets and MCAP recordings.” Explain why you built it and stay available for questions. | Feedback on the usable tool. HN requires something people can try and prohibits soliciting upvotes or comments. |

LeRobot's own README links its Discord and describes the dataset workflow, which makes it a strong first audience. Foxglove's community page explicitly welcomes robotics engineers and discussion of data formats. These are audience-fit inferences from the [LeRobot project](https://github.com/huggingface/lerobot) and [Foxglove community description](https://foxglove.dev/community), not endorsements of Physlint.

I would postpone paid ads, Product Hunt, and a broad multi-platform launch until several independent users have run a dataset. Early conversations can reveal a bad default or an installation problem faster than a large burst of traffic.

## Two-week sequence

1. Days 1–2: verify the exact public install route, prepare the short video and example report, and publish one LeRobot community post. Record each installation problem.
2. Days 3–5: personally help the first five volunteers interpret reports. Prepare individual maintainer notes. Fix false positives before reusing their stories as marketing examples.
3. Days 6–8: write one technical walkthrough using a reviewed result. Share a separate MCAP/ROS 2 example in the relevant communities.
4. Days 9–11: share the short video on LinkedIn and X with the walkthrough. Offer a minimal CI integration example to maintainers who found the CLI useful.
5. Days 12–14: publish a Show HN submission when the install path is reliable and someone can try the demo immediately. Follow up with volunteers about a second run or a CI trial.

Do not duplicate the same post across unrelated channels. LeRobot users care about episode, action, and video defects; ROS users care about recordings, topics, schemas, and clocks. Match the example to the reader.

## Suggested social post

I injected one NaN into a tiny robot-learning dataset. Physlint pointed to the episode, action stream, sample, and dimension that contained it.

I built it to check robot data before training. It runs locally, supports LeRobot v3 and MCAP recordings, and produces JSON reports for agents and CI.

The clip shows the synthetic test. I'm looking for five dataset maintainers to try their own data and tell me where the checks are wrong or incomplete.

Demo and installation: https://github.com/pranayjoshi/physlint

## Measure adoption

Keep a small manual log of the source channel, independent maintainer, dataset revision, first completed run, feedback classification, and repeat run or CI trial. Do not request private recordings for the log.

For two weeks, aim for five independent maintainers completing a check, three useful conversations about findings, and two repeat users or CI trials. These are targets, not existing results. Review GitHub referrals and video completion alongside those outcomes. Stars and PyPI downloads alone do not show that anyone validated a dataset.

After the first five trials, improve the tool and message around the failures those users actually encountered. Expand adapters only when a willing user supplies representative data and an acceptance test.

## Assets

- `docs/assets/launch/exports/physlint-launch-social.mp4`: 1080×1350, 18 seconds, for native feed uploads.
- `docs/assets/launch/exports/physlint-launch.mp4`: 1920×1080, 18 seconds, for the repository and widescreen embeds.
- `docs/assets/launch/exports/physlint-launch.vtt`: text alternative and caption transcript.
- `docs/assets/launch/exports/physlint-launch-evidence.json`: the sample values and finding used by the renderer.

The clip is silent and can be understood with autoplay muted. If you add narration later, describe the controlled test; avoid invented training losses, GPU costs, customer results, or performance claims.
