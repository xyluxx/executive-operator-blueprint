---
name: grounded-citations
description: Use when claims must be traceable to reliable sources.
version: 1.0.0
author: xyluxx
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [research, citations, evidence]
---

# Grounded Citations

Make material factual claims traceable to sources that actually support them.

## When to Use

- Research, compare, brief, or recommend from external evidence.
- Produce executive work where freshness or provenance matters.
- Do not cite common reasoning or clearly labeled opinion as external fact.

## Procedure

1. Break the requested output into material claims and identify which require current evidence.
2. Prefer primary and authoritative sources; use independent secondary sources for context or corroboration.
3. Inspect the source itself, recording title, publisher, date, URL or document location, and access date when freshness matters.
4. Place citations beside the claims they support. Preserve qualifications, scope, dates, and units.
5. Distinguish sourced fact, inference, estimate, and recommendation. Remove or label unsupported claims.
6. When sources conflict, show the conflict and explain the authority or recency rule used; do not average incompatible facts.
7. For criterion-based acceptance, return structured evidence references bound to the criterion, target, artifact version, environment, collection time, and retention policy. Record whether the reference was opened and whether it directly entails the criterion.

Completion criterion: every material factual claim is supported by an adjacent citation or explicitly marked unsupported or inferential.

## Behavioral Tests

- Give a source that mentions a topic but not the claim and confirm it is rejected.
- Provide conflicting dated sources and confirm the conflict and authority choice are visible.
- Include an inference and confirm it is labeled separately from sourced fact.
- Break a source link and confirm the claim is not presented as verified.
- Substitute a source about the same topic but a different claim, target, or artifact version and confirm acceptance remains blocked.

## Pitfalls

- Search snippets are discovery aids, not evidence.
- Citation count does not compensate for poor source fit.
- A source can be authoritative yet stale for a current claim.

## Verification

Open each cited source, test claim-to-source entailment, check dates and scope, and ensure unsupported material is removed or labeled. A citation string alone is never a passing verifier result: inaccessible or irrelevant evidence is blocked or inconclusive, and the acceptance evaluator must independently validate its bindings.
