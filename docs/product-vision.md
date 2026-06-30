# Product Vision

Editorial Platform is an editorial workflow platform for producing evidence-based
publications with clear provenance, explicit workflow, and interchangeable participants.

The platform helps editors acquire source material, extract evidence, evaluate relevance,
generate proposals, record reviews, and publish decisions. It is not only a newsletter
generator, and it is not an AI wrapper. The BIS newsletter is the reference implementation
and validation scenario for a broader editorial platform.

## Key Concepts

### Immutable Artefacts

Editorial work is represented as immutable artefacts. Articles, Extractions, Evaluations,
OptimisationRequests, IssueProposals, Reviews, Publications, and WorkflowEvents are records
of what happened. New evidence, judgement, or output creates a new artefact rather than
rewriting history.

### Explicit Workflow

Workflow is recorded explicitly through WorkflowEvents. State is derived from event history
rather than stored inside artefacts. This keeps editorial decisions visible and auditable.

### Interchangeable Participants

Participants are interchangeable. A workflow can use deterministic processors, human
editors, AI-assisted processors, or future integrations without changing the core
architecture.

### Deterministic And AI Participants

The platform supports deterministic and AI participants side by side. Deterministic
participants provide predictable behaviour. AI participants provide assistance where
language understanding, summarisation, judgement support, or interpretation can help.

### Optimisation Proposes

Optimisation creates IssueProposal records. A proposal is not an approved issue, a
publication, or a decision. It is a structured suggestion that editors can inspect, compare,
review, and accept or reject through workflow.

### Reviews Decide

Reviews record editorial judgement. They can approve, reject, request changes, or comment
on any artefact. Reviews do not mutate proposals or trigger hidden workflow.

### Publication Records Decisions

Publications record the editorial output that has been chosen. They are
presentation-independent artefacts that can be rendered by publishers such as the Markdown
publisher.

### Provenance Throughout

Every meaningful contribution should carry provenance: who or what produced it, what input
it used, which provider or processor ran, and what version or configuration shaped the
result. AI contributions must be attributable and inspectable.

## Guiding Principles

1. Artefacts are immutable.
2. Workflow is explicit.
3. Participants are interchangeable.
4. AI augments editorial judgement.
5. Optimisation proposes rather than decides.
6. Human reviewers remain authoritative.
7. Every AI contribution carries provenance.
8. CLI is the canonical interface.
9. Future interfaces, including web and API interfaces, build on the same application layer.
10. The BIS newsletter serves as the reference implementation and validation scenario.
