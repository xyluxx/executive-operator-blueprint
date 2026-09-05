---
name: growth-intelligence
description: Use when analyzing marketing, SEO, or market demand.
version: 1.0.0
author: xyluxx
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [Marketing, Analytics, SEO, Research]
    related_skills: [integration-onboarding, grounded-citations]
---

# Growth Intelligence

Use this skill for advertising, analytics, attribution, SEO, keywords, local search, competitor research, market demand, and growth recommendations.

This skill is an intelligence layer. It does not authorize campaign, budget, tracking, publishing, or website changes.

See `references/dataforseo.md` for one optional keyword and search-data provider pattern.

## When to Use

1. Review advertising performance.
2. Reconcile leads, calls, bookings, sales, and analytics.
3. Research keyword demand or search results.
4. Audit local or technical SEO.
5. Compare competitors or locations.
6. Prepare a recurring performance report.
7. Investigate a suspected tracking or reporting problem.

## Provider Options

Examples include:

1. Direct advertising platform APIs
2. Google Analytics 4
3. Search Console
4. Google Business Profile
5. DataForSEO
6. Google Places
7. Firecrawl or another crawler
8. A marketing data aggregator
9. CRM and revenue records
10. Call tracking and booking systems

Use available providers. Do not silently substitute a source with different coverage.

## Data Contract

Every metric must carry:

1. Business and account
2. Source
3. Time range
4. Timezone
5. Currency or unit
6. Attribution definition
7. Conversion definition
8. Freshness
9. Missing data
10. Query or evidence pointer

## Analysis Procedure

1. Lock the business, account, date range, and objective.
2. Read current definitions before comparing periods.
3. Pull each source independently.
4. Reconcile totals by identity and event definition.
5. Separate visits, leads, calls, form submissions, booking clicks, completed bookings, and sales.
6. Detect tracking gaps, lag, duplication, and source coverage.
7. Compare performance only where definitions are compatible.
8. Distinguish source fact, observation, and recommendation.
9. Recommend staged changes with expected evidence.
10. Keep all mutations pending the configured approval policy.

Completion criterion: conclusions reproduce from named sources and incompatible metrics are not combined.

## SEO and Keyword Procedure

1. Define one search intent and geography.
2. Pull keyword volume, competition, cost, result features, and trend where available.
3. Inspect the live results page or approved SERP source.
4. Verify real competitors and business categories.
5. Check site content, crawlability, speed, indexation, and local signals as applicable.
6. Prefer useful, truthful pages over scaled filler.
7. Keep provider estimates labeled as estimates.
8. Recheck availability and current state before domain or content decisions.

DataForSEO is one useful provider for keyword and search data. Another provider may implement the same contract.

## Reporting

A report should answer:

1. What happened
2. What changed
3. Which evidence supports it
4. What is uncertain
5. What should remain untouched
6. What small next decision is justified
7. How the result will be measured

Use the audience’s preferred detail level. Keep technical diagnostics in an appendix or private record unless requested.

## Approval Defaults

Reading, reconciliation, research, and private recommendations may proceed within approved accounts.

Require approval for:

1. Spend or budget
2. Bids and targeting
3. Campaign status
4. Conversion definitions
5. Tracking and tags
6. Website publishing
7. Business listing changes
8. Bulk content or domain purchases

## Pitfalls

1. Do not infer completed sales from page visits or clicks.
2. Do not combine accounts belonging to different businesses.
3. Do not treat reporting delay as a tracking failure without evidence.
4. Do not recommend aggressive cuts from one short period.
5. Do not present estimated traffic or backlinks as verified facts.
6. Do not change a conversion definition while comparing historical performance.
7. Do not call a connector complete because one dashboard loads.

## Verification

1. Account identity is explicit.
2. Date range and timezone match across sources.
3. Conversion definitions are recorded.
4. Totals reconcile or differences are explained.
5. One known metric reproduces from the source.
6. Missing coverage is visible.
7. No mutation occurred without approval.
8. Approved mutations have live provider readback.
9. Recurring reports deduplicate and use current data.
10. Provider failure does not produce invented numbers.
