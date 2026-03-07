---
name: ashare-policy-stock-watch
description: Use this skill when the user wants current A-share stock ideas filtered by recent policy direction, sector themes, and practical trading constraints such as a share price cap below CNY 100.
---

# Ashare Policy Stock Watch

## Overview

Use this skill to build or refresh a short list of A-share candidate stocks that fit current national or provincial policy direction and satisfy simple execution filters such as `price <= 100 CNY`.

The skill is for research support, not personalized investment advice. Always present candidates as `policy-aligned watchlist names` with clear risks, dates, and sources.

Load [references/workflow.md](./references/workflow.md) when you need the detailed filtering workflow and output template.

## When To Use

Use this skill when the user asks for any of the following:

- Recommend a few A-share stocks based on current policy themes
- Refresh a watchlist of sectors or stocks tied to recent government policy
- Filter A-share names by policy direction plus a price ceiling such as `<= 100`
- Produce a reusable routine for periodically updating policy-driven stock candidates

## Workflow

1. Identify the latest policy themes from primary sources first.
   Prioritize `gov.cn`, `ndrc.gov.cn`, `miit.gov.cn`, `csrc.gov.cn`, major exchange notices, and provincial government policy pages when local support matters.

2. Convert policy language into investable sectors.
   Examples: low-altitude economy, embodied AI and robotics, commercial aerospace, advanced materials, industrial AI, new energy equipment.

3. Screen candidate A-shares.
   Apply at minimum:
- `latest observed share price <= 100 CNY`
- not `ST` or `*ST`
- not suspended if that information is available
- avoid names with obviously poor liquidity when turnover data is easy to verify
- prefer companies with business linkage that is specific, not only concept-tag driven

4. Produce a compact watchlist.
   For each stock include:
- ticker and company name
- sector or theme
- policy driver
- latest observed price and date
- why it fits
- one key risk

5. Add cautionary framing.
   State that prices and policy interpretation can change quickly and should be rechecked before trading.

## Output Rules

- Keep the list short, usually `3 to 7` names.
- Use current web verification for price-sensitive facts.
- Include exact dates when saying `latest`, `recent`, `today`, or `current`.
- Separate `policy fit` from `trading quality`; do not imply a policy theme alone is a buy signal.
- If policy support is broad but the stock linkage is weak, say so explicitly.
- Do not present the output as certain or guaranteed.

## Default Response Shape

Use a structure close to this:

1. `Policy themes worth watching`
2. `Filtered A-share candidates`
3. `Risks and what to recheck next`

For each candidate, prefer one line like:

`000099 CITIC Offshore Helicopter | low-altitude economy | latest observed price about XX CNY on YYYY-MM-DD | policy fit: ... | risk: ...`

## Resources

### references/
Use [references/workflow.md](./references/workflow.md) for:
- source priority
- policy-to-sector mapping
- screening checklist
- output template
