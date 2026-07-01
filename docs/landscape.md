Editorial Platform in Context

Introduction

Editorial Platform draws inspiration from several established areas of software engineering, including content management systems, workflow engines, scientific workflow platforms, optimisation systems and AI engineering frameworks.

It is not intended to replace any of these categories. Instead, it combines ideas from each to support a different problem: evidence-based editorial decision-making.

Traditional publishing systems typically assume that the content to be published has already been selected. Editorial Platform instead models the complete editorial process, beginning with a corpus of candidate material and ending with an approved publication.

Its objective is not simply to publish content, but to make the editorial decision-making process transparent, reproducible and extensible.

⸻

Conceptual Influences

Editorial Platform combines ideas from several disciplines.

Discipline	Influence on Editorial Platform
Editorial Practice	Human review, editorial judgement, publication workflows
Workflow Systems	Explicit workflows, task orchestration, approvals
Operations Research	Multi-objective optimisation, decision support, constraint handling
Scientific Computing	Provenance, reproducibility, immutable artefacts
Knowledge Management	Structured editorial metadata and derived information
Artificial Intelligence	AI participants for extraction, evaluation and future editorial assistance

Rather than focusing exclusively on one of these areas, Editorial Platform integrates them into a single editorial workflow.

⸻

Comparison with Content Management Systems

Examples include:

* Open Journal Systems (OJS)
* OpenCms
* Enonic XP

Content management systems provide excellent support for:

* authoring;
* document management;
* editorial permissions;
* publication workflows; and
* website delivery.

These systems generally assume that content has already been created and selected.

Editorial Platform addresses an earlier stage of the publishing lifecycle.

Instead of asking:

“How should this document be published?”

it asks:

“Which documents should become part of the publication?”

This distinction influences the entire architecture.

Editorial Platform therefore focuses on:

* acquisition of candidate material;
* automated extraction;
* editorial evaluation;
* optimisation;
* human review; and
* publication provenance.

It is complementary to a traditional CMS rather than a replacement.

⸻

Comparison with Workflow Engines

Examples include:

* Flowable
* Camunda

Workflow engines specialise in:

* business processes;
* approvals;
* task assignment;
* workflow execution; and
* audit trails.

Editorial Platform shares many of these ideas.

Both model explicit workflows rather than embedding process logic throughout an application.

The difference lies in the domain model.

Workflow engines provide generic concepts such as tasks and processes.

Editorial Platform introduces editorial concepts such as:

* Article;
* Extraction;
* Evaluation;
* OptimisationRequest;
* IssueProposal;
* Review; and
* Publication.

The result is a workflow engine specialised for editorial decision-making.

⸻

Comparison with Scientific Workflow Platforms

Examples include:

* AiiDA

Scientific workflow platforms emphasise:

* provenance;
* reproducibility;
* immutable data;
* computational workflows; and
* reproducible research.

Editorial Platform adopts many of these principles.

Each stage of an editorial workflow produces immutable artefacts that preserve the complete history of editorial decisions.

This allows publications to be:

* reproduced;
* inspected;
* audited; and
* explained.

Although the application domains differ considerably, the architectural principles are closely aligned.

⸻

Comparison with AI Engineering Frameworks

Examples include:

* LangChain
* Haystack
* LlamaIndex

These frameworks provide powerful abstractions for building applications around large language models.

Editorial Platform makes use of AI in a different way.

Rather than treating an LLM as the centre of the application, Editorial Platform models AI as one type of participant within a broader editorial workflow.

For example, an extraction may be produced by:

* a deterministic algorithm;
* a large language model; or
* a human editor.

Likewise, article evaluation may be performed by deterministic rules, AI models or human reviewers.

The workflow remains unchanged because participants are interchangeable.

This separation allows AI capabilities to evolve without altering the surrounding editorial architecture.

⸻

What Makes Editorial Platform Different?

Editorial Platform combines several ideas that are rarely found together in a single open-source project.

These include:

* explicit editorial workflows;
* immutable editorial artefacts;
* optimisation-driven publication construction;
* interchangeable deterministic, AI and human participants;
* complete workflow provenance;
* human editorial approval before publication; and
* multiple publication renderers built upon a common publication model.

The platform is therefore neither a traditional content management system nor an AI content generation tool.

Instead, it is an editorial workflow platform centred on transparent and reproducible editorial decision-making.

⸻

Comparison Summary

Capability	CMS	Workflow Engine	AI Framework	Editorial Platform
Editorial workflows	✓	✓	△	✓
Candidate content acquisition	△	✗	△	✓
Automated extraction	△	✗	✓	✓
Automated evaluation	✗	✗	✓	✓
Multi-objective optimisation	✗	✗	△	✓
Human editorial review	✓	✓	✗	✓
Immutable editorial artefacts	△	△	✗	✓
Workflow provenance	△	✓	△	✓
AI participants	✗	✗	✓	✓
Multiple renderers	✓	✗	✗	✓

Legend:

* ✓ — core capability
* △ — partially supported or achievable with additional implementation
* ✗ — generally outside the scope of the platform

⸻

Positioning

Editorial Platform occupies a distinct position within the publishing software landscape.

Most publishing systems begin with content and manage its publication.

Editorial Platform begins with a corpus of candidate material and models the decision-making process that determines what should be published.

By combining editorial workflows, optimisation, provenance, artificial intelligence and human review, Editorial Platform aims to provide an extensible foundation for evidence-based editorial decision-making.

As the platform evolves, new providers, extractors, evaluators, optimisers, renderers and user interfaces can be introduced without changing the underlying editorial model. This separation of concerns is one of the platform’s fundamental architectural principles.
