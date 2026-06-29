# Philosophy

## Vision

Editorial Platform is an extensible framework for evidence-based editorial decision making.
It is not just a newsletter generator. The BIS newsletter is the first reference application:
a concrete proving ground for a broader configurable editorial architecture.

The platform should help editorial teams acquire material, extract evidence, evaluate
relevance and quality, optimise selections, record reviews, and publish outputs with clear
provenance.

## Design Principles

Capabilities should be independent and configurable. A publication can choose different
providers, extractors, evaluators, optimisers, review workflows, and publishers without
rewriting the platform core.

The architecture should support deterministic algorithms, statistical methods,
optimisation, and AI-assisted processing. No single technique owns the architecture.

## Evidence Before Decisions

Editorial decisions should be grounded in explicit evidence. Articles are acquired first,
then Extractions and Evaluations build an auditable evidence trail before optimisation,
review, or publication.

## Immutable Editorial Artefacts

Editorial artefacts should be immutable records. A new interpretation, score, proposal, or
review should create a new artefact or workflow event rather than mutating the historical
record.

This applies especially to IssueProposal records. An IssueProposal is an optimiser output,
not an approved issue, and it should not be rewritten by review.

## Explicit Workflow

Workflow state and decisions should be explicit. Reviews do not modify proposals.
Re-optimisation should happen through an explicit OptimisationRequest. Significant actions
should be represented by WorkflowEvent records so the path from evidence to publication can
be reconstructed.

ApprovedIssue should not be introduced as a domain object. Approval should be represented
through workflow events and state derived from those events.

## Progressive Intelligence

The platform should support progressively richer intelligence. Early stages can use simple
deterministic processors. Later stages can add statistical models, optimisation algorithms,
and AI-assisted processors without changing the core workflow concepts.

## AI As Participant

AI is a participant in the processing architecture, not the architecture itself. AI may act
as a provider, extractor, evaluator, optimiser, reviewer assistant, or publisher assistant.
Its outputs should be stored, attributed, and auditable like other processor outputs.

## Configurability

Publications should be defined through configuration. The same core pipeline should support
different editorial goals, policies, sources, scoring rules, optimisation settings, and
publication formats.

## Provenance And Auditability

Every material processing step should preserve provenance: what ran, when it ran, what input
it used, and what output it created. This makes editorial decisions inspectable, repeatable,
and contestable.

## Human Editorial Judgement Remains Final

The platform can organise evidence and propose decisions, but human editorial judgement
remains final. Review and publication should make human decisions visible rather than hide
them inside processor outputs.
