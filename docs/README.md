# Documentation

Start with the [README](../README.md) for what Thought Pins is and how to run it locally.
This index is everything else.

Root-level files are the contracts consulted most often; the folders below hold supporting
material grouped so each surface stays easy to audit.

## Start here

| | |
| --- | --- |
| [ARCHITECTURE_MODULES.md](../ARCHITECTURE_MODULES.md) | Which module owns which concern. **Read before adding a feature.** |
| [TECHNICAL_REVIEW_GUIDE.md](architecture/TECHNICAL_REVIEW_GUIDE.md) | A reviewer's tour of the codebase with a verification path |
| [RUNNING.md](operations/RUNNING.md) | Full local setup, the API surface, and pre-deploy checks |
| [TECHNICAL_SPEC.md](../TECHNICAL_SPEC.md) | The build order and system specification |
| [AGENTS.md](../AGENTS.md) | Conventions for AI coding agents working in this repo |

## Architecture

| | |
| --- | --- |
| [MEMORY_ARCHITECTURE_REVIEW.md](architecture/MEMORY_ARCHITECTURE_REVIEW.md) | The memory design and its honest gaps, graded |
| [MEMORY_SALIENCE.md](architecture/MEMORY_SALIENCE.md) | How importance is estimated and bounded |
| [SOCIAL_EPISODIC_RELEVANCE.md](architecture/SOCIAL_EPISODIC_RELEVANCE.md) | Query-conditioned ranking over social and episodic detail |
| [EXTERNAL_MEMORY_BENCHMARKS.md](architecture/EXTERNAL_MEMORY_BENCHMARKS.md) | Dataset governance, calibration, holdout metrics, benchmark limits |
| [OBSIDIAN_INTEROPERABILITY.md](architecture/OBSIDIAN_INTEROPERABILITY.md) | The versioned vault export/import contract |
| [MOBILE_API_CONTRACT.md](architecture/MOBILE_API_CONTRACT.md) | The iOS/Android API contract |
| [APP_CORE_FOUNDATION.md](architecture/APP_CORE_FOUNDATION.md) | UI-free application primitives |
| [LOCAL_DEVICE_STORAGE.md](architecture/LOCAL_DEVICE_STORAGE.md) | On-device storage rules |
| [PLATFORM_CODEBASE_STRATEGY.md](architecture/PLATFORM_CODEBASE_STRATEGY.md) | Web, iOS, Android, and repository strategy |
| [TECHNICAL_DEBT_REGISTER.md](architecture/TECHNICAL_DEBT_REGISTER.md) | Known debt, tracked rather than forgotten |

## Operations

| | |
| --- | --- |
| [RUNNING.md](operations/RUNNING.md) | Local development through production configuration |
| [PRODUCTION_RUNBOOK.md](operations/PRODUCTION_RUNBOOK.md) | Deploy, rollback, backup, restore, launch checks |
| [PRODUCTION_PLAN.md](operations/PRODUCTION_PLAN.md) | The detailed build order to a serious launch |
| [PRODUCTION_DECISION.md](operations/PRODUCTION_DECISION.md) | Hosting and infrastructure decisions, with reasoning |
| [BACKEND_RELEASE_CHECKLIST.md](operations/BACKEND_RELEASE_CHECKLIST.md) | The backend release gate |
| [WEB_APP_RELEASE_CHECKLIST.md](operations/WEB_APP_RELEASE_CHECKLIST.md) | The backend-served web app gate |

## Product

| | |
| --- | --- |
| [PRODUCT.md](product/PRODUCT.md) | What the product does and why |
| [PERSONALITY_SPEC.md](product/PERSONALITY_SPEC.md) | Response personality contracts |
| [PRICING_PLAN.md](PRICING_PLAN.md) | Cost model and free-tier reasoning |
| [DESIGN.md](../DESIGN.md) · [DESIGN_SYSTEM.md](../DESIGN_SYSTEM.md) | Product design direction and the type/colour/motion system |

## Release

| | |
| --- | --- |
| [OPEN_SOURCE_RELEASE_CHECKLIST.md](release/OPEN_SOURCE_RELEASE_CHECKLIST.md) | What must be true before the repository goes public |
| [FREE_LAUNCH_POLICY.md](release/FREE_LAUNCH_POLICY.md) | The machine-checked no-monetisation contract |
| [PRIVACY_AND_STORE_READINESS.md](release/PRIVACY_AND_STORE_READINESS.md) | App Store and Play Store privacy readiness |
| [RELEASE_VERSIONING.md](release/RELEASE_VERSIONING.md) | Backend, web, iOS, and Android versioning |
| [APP_STORE_APPROVAL_PLAN.md](release/APP_STORE_APPROVAL_PLAN.md) · [APP_REVIEW_RISK_REGISTER.md](release/APP_REVIEW_RISK_REGISTER.md) | Submission plan and review risks |
| [APPLE_REVIEW_ANSWERS.md](release/APPLE_REVIEW_ANSWERS.md) · [LEGAL_REVIEW_NOTES.md](release/LEGAL_REVIEW_NOTES.md) | Prepared reviewer answers and legal notes |
| [MACOS_XCODE_APP_STORE_RUNBOOK.md](release/MACOS_XCODE_APP_STORE_RUNBOOK.md) · [MAC_XCODE_V1_EXECUTION_CHECKLIST.md](release/MAC_XCODE_V1_EXECUTION_CHECKLIST.md) | The native release procedure |

## Elsewhere

Public legal text is maintained in [`site/`](../site/) and published at thoughtpins.com.
Store-console evidence lives in [`deploy/store/`](../deploy/store/). Founder-only runtime
material stays under [`founder/`](../founder/) and is excluded from public and native release
artifacts. Historical design handoffs are retained outside this repository.
