# ADR-0003: Immutable editorial artefacts and explicit workflow events

**Status:** Accepted

## Context

The platform now stores acquired Articles, derived Extractions, Evaluations, and
IssueProposal records. Future workflow stages will add review and publication.

To keep the platform auditable, repeated processing and human decisions must not obscure
the evidence trail that led to a proposal or publication.

## Decision

Editorial artefacts are immutable.

Significant editorial actions create new artefacts or workflow events.

Reviews are recorded separately from proposals.

Re-optimisation is driven by explicit OptimisationRequests.

Publication is downstream of workflow decisions, not a direct optimiser output.

IssueProposal is not an approved issue. ApprovedIssue should not be introduced as a domain
object; approval belongs in explicit workflow events and derived workflow state.

## Consequences

This gives the platform better provenance and auditability.

It becomes easier to support multiple proposals, multiple reviewers, repeated optimisation,
and comparisons between alternative editorial paths.

The system will have more records to store and manage.

Workflow logic must be explicit rather than implicit.

Review and publication features need to read workflow state instead of mutating optimiser
outputs.
