---
name: pr-operator
description: Use when monitoring PR and preparing approved pitches.
version: 1.0.0
author: xyluxx
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [Public Relations, Outreach, Monitoring, CRM]
    related_skills: [integration-onboarding, grounded-citations]
---

# PR Operator

Use this skill to monitor approved public relations sources, evaluate opportunities, prepare pitches, log activity, watch replies, and notify the owner about material wins.

This skill replaces a private application with a reusable operating contract. It requires onboarding before the first run.

See `references/background-duty.md` for the recurring collector, qualification, draft, reply, and notification pattern.

## When to Use

1. Monitor journalist, podcast, event, award, or publication opportunities.
2. Research whether an opportunity fits the approved brief.
3. Draft a pitch in the configured voice.
4. Queue a pitch for approval.
5. Record sent pitches and replies.
6. Notify on a qualified opportunity, reply, interview, mention, or win.
7. Build a recurring background PR duty.

## Required Onboarding

Capture:

1. Organization and offer
2. Approved representative and title
3. Pitch voice and length
4. Required introduction and positioning
5. Target audiences, publications, topics, and geographies
6. Qualification criteria
7. Evidence and claims allowed
8. Prohibited claims, industries, and topics
9. Approval and sending policy
10. Source list and search terms
11. CRM destination and object map
12. Notification route
13. Win definition
14. Retention and unsubscribe policy

No monitoring or drafting begins until the brief is internally consistent.

## Opportunity Record

Store:

1. Source and external ID
2. Publication or host
3. Opportunity title
4. Topic and audience
5. Deadline and timezone
6. Requirements
7. Contact identity
8. Fit reason
9. Risk or uncertainty
10. Status
11. Draft version
12. Approval
13. Sent record
14. Reply and outcome
15. CRM record ID
16. Evidence

## Background Workflow

1. Poll only approved sources at the configured cadence.
2. Normalize and deduplicate by source ID, URL, contact, topic, and deadline.
3. Reject expired, prohibited, duplicate, or clearly irrelevant items deterministically.
4. Research the remaining opportunity and publication.
5. Score fit against the saved criteria.
6. Draft only when the threshold is met.
7. Save the pitch with its opportunity record.
8. Request approval if required.
9. Send only through the approved account and policy.
10. Read back the sent record.
11. Watch replies and update the CRM.
12. Notify only for material opportunities, needed decisions, replies, failures, or wins.

Completion criterion: every pitch and outcome traces to one opportunity, one approved representative, one sent record, and one CRM record.

## Pitch Rules

1. Use the configured human voice.
2. Lead with relevance, not generic praise.
3. Make only supportable claims.
4. Respect the requested format and deadline.
5. Avoid tool names unless the brief specifically calls for them.
6. Never invent credentials, awards, customers, metrics, or availability.
7. Keep follow ups within the configured cadence and stop rules.

## CRM Integration

Provider examples include Twenty, Salesforce, HubSpot, Pipedrive, Airtable, Notion, or a custom database.

Log:

1. Contact and organization
2. Opportunity source
3. Pitch version
4. Sent time and account
5. Follow up due
6. Reply status
7. Interview or placement
8. Final outcome

Use the CRM’s stable identities and avoid duplicate contacts.

## Approval Defaults

1. Source monitoring may run automatically.
2. Qualification and private drafts may run automatically.
3. Sending requires exact approval unless the owner explicitly authorizes a bounded standing campaign.
4. Spending, publishing, calendar booking, and account changes require approval.
5. Standing authority must name audience, sender, template boundary, cadence, volume, budget, and expiration.

## Pitfalls

1. Do not scrape or email sources against their terms.
2. Do not send because a draft exists.
3. Do not treat every reply as a win.
4. Do not notify the owner about unchanged monitoring runs.
5. Do not store private client facts in a reusable skill.
6. Do not let an old pitch voice override current onboarding.
7. Do not lose the relationship between the opportunity, pitch, reply, and CRM record.

## Verification

1. Onboarding completeness check passes.
2. Duplicate source items collapse.
3. Expired and prohibited examples are rejected.
4. Qualified examples produce a compliant private draft.
5. Unapproved sending is blocked.
6. Approved synthetic send is read back when a test account is available.
7. CRM record is created once.
8. Reply updates the same record.
9. Material win notifies the selected route once.
10. Source or provider failure produces a bounded alert, not invented opportunities.
