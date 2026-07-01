# BIS Newsletter Tutorial

This tutorial validates Editorial Platform using the RSS Business & Industrial Section newsletter as the reference implementation.

The aim is to produce a draft newsletter using the existing CLI workflow by covering the following areas:

1. What the BIS newsletter is
2. Why this is the reference implementation
3. How the BIS publication configuration is structured
4. How to build and inspect the corpus
5. How extraction and evaluation support editorial judgement
6. How optimisation creates a proposal
7. How review turns a proposal into an editorial decision
8. How publication and rendering differ
9. What the first validation run taught us

## Goal

Produce a BIS newsletter from configured sources through:

1. Ingestion
2. Extraction
3. Evaluation
4. Optimisation
5. Review
6. Publication
7. Markdown rendering

## Setup

```bash
git checkout main
git pull
rm -f bis-validation.sqlite
```
