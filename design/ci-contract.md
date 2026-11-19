# GitHub CI and deployments API v1

The reader uses the owner's existing GitHub CLI sign-in on this computer.
The owner opts in under Settings → Sources. GitHub CI observes repositories
across agent sources, so it has a sibling preference and feed rather than
an agent adapter in the harness catalog. The harness catalog stays unchanged.

## Private routes

All routes retain the owner-authenticated Sources v1 transport, exact path and
no-store responses. POST uses the usual JSON and X-Progress-Desk headers.

- GET /api/sources/v1/ci/settings → `{version:1,enabled:boolean}`. Default false.
- POST /api/sources/v1/ci/settings accepts exactly `{enabled:boolean}` and returns
  the same shape as GET. This preference never signs in to or modifies GitHub.
  Turning it off drops current observations and suppresses pending alerts.
- GET /api/sources/v1/ci → `{version:1,ci:Outcome}`. Reads the latest observation
  without blocking on GitHub. Source v1 glance and legacy v2 shapes are unchanged.

All outcomes use `{status,attemptedAt,checkedAt,reason,data}` from the
[common contract](api-contract.md#common-outcome-object). A successful discovery
has `data:{rows:[Row],omitted:boolean}`. An empty complete discovery is quiet.
`omitted` signals that discovery was partial or hit a safety bound. Do not use
a quiet result or a count of zero for an unavailable observation.

## Rows

```text
Row = {
  repo: "owner/name", branch: string,
  agentIds: [string], pr: {number, url} | null,
  ci: Outcome<{
    state: running | passed | failed | cancelled | none,
    total: integer, passed: integer, failed: integer, running: integer,
    url: string, updatedAt: ISO timestamp | null
  }>,
  deploy: Outcome<{
    environment: string, state: queued | pending | in_progress |
      success | failure | error | inactive | waiting | unknown,
    url: string, updatedAt: ISO timestamp
  }>
}
```

Join agent IDs to the existing active and Ended agent rows. Check the row's
outcome before rendering its fields. CI and deployment checks can fail
independently. The check rollup is for the GitHub branch tip. An open PR for that tip supplies
the PR link and its rollup when available. Failed takes precedence
over running, then cancelled and passed. Neutral/skipped checks count toward
total and do not count toward passed. No checks is state `none`. The deployment is the newest match from the tip commit's deployments and the
30 newest repository deployments. That includes deployments recorded by SHA and
branch-ref deployments from older commits. If the bounded repository sample is
incomplete and contains no match anywhere, the deployment outcome is unavailable
with `coverage_incomplete`. A complete empty result is quiet with null data. A deployment without a
status is shown as unknown. Links are constructed GitHub URLs. Remote text such
as PR titles, check labels and deployment target URLs is omitted. The deployment
label is a short environment name or a generic label if unsafe to display.

## Discovery and polling

Use fresh locally observed T3, Claude Code and Codex activity. T3 worktree and
branch take precedence over the project root. A named T3 branch is resolved against the repository in its worktree. An
ended row with a removed worktree may use its project repository and explicit
branch to find a historical PR. Claude captures only the GitHub repo and branch
on its next lifecycle hook after opt-in. Tailnet workspaces are skipped. Resolve
GitHub remotes privately and group by repo and branch, with active work first
and a maximum of 20 pairs. Local paths and Git remotes never leave discovery.

A non-repository workspace, detached HEAD, Claude session without Git evidence,
or branch missing on GitHub contributes no CI row. A deleted branch can still
contribute an ended PR result. A genuine discovery failure or bound contributes
to `omitted`.

Each due branch uses one GraphQL request for checks, deployments and any
historical PR. Active branches poll every 30 seconds while work is pending,
for up to 10 minutes per continuous pending period on the same tip. Other
active branches poll every 120 seconds, and ended-only branches every 10
minutes. The PR attention feed polls separately per repository on the settled
or ended cadence. CI failures back off per branch and PR attention failures
back off per repository. CI keeps its polling cadence when only
the deployment read fails. Rate limiting, sign-out and a failure across all watched branches
pause the GitHub batch.
Sign-out retries stay within three minutes.
Requests use read-only GitHub CLI subprocesses with explicit GitHub host,
bounded output and timeouts, and no inherited credential variables, diagnostic
output or prompts. Only GitHub receives repository and ref selectors.

Closed reasons are `disabled`, `checking`, `coverage_incomplete`, `not_github`,
`gh_missing`, `gh_signed_out`, `cannot_reach_github`, `rate_limited`,
`repo_not_found`, and `invalid_response`. Disabled and missing CLI or sign-in
yield `not_set_up`. In-flight initial reads and failures yield `unavailable`
with the attempt time, null data and any known last successful time.

## Notifications

A fresh failed rollup generates one pending `ci_failed` notification per
repository and commit SHA, including a failing SHA seen on the first poll.
No alert is generated by stale observations or transport failures. Durable
deduplication survives reader restarts and toggling the preference. The SHA
stays internal. Use the existing Sources v1 list and reserve/claim/release
routes with sourceId `github-ci` and this event shape:

```text
{id, kind:"ci_failed", repo, occurredAt, links:{desktop:null,web:null}}
```

Native CI banners open Nagi. The Linux tray displays a failure indicator when any
current CI row is freshly failed. The reader reports missing gh as not_set_up on
both platforms.

## Pull requests waiting on the owner

GET /api/sources/v1/ci/pulls → `{version:1,pulls:Outcome}`.

Success data is `{count,rows,omitted}`. Count is the number of returned
actionable PRs. When omitted is true, present the count as partial. Consider
non-draft open PRs in watched repositories when their head matches a watched
branch or the GitHub CLI's signed-in viewer authored them. Reasons in priority
order are an outstanding personal review request (`review_requested`), a
changes-requested decision (`changes_requested`), and a mergeable PR with
passing or absent checks (`ready_to_merge`). Readiness requires approval and
a `CLEAN` or `HAS_HOOKS` merge state, or no review decision and a `CLEAN`
merge state. A required review or requested changes prevents merge readiness.
A row has `{repo,number,title,url,why,ci,updatedAt}`. CI is the row's CI state
string or null if unavailable. Titles are short sanitized GitHub text, with a generic
PR label when unsafe. Only a successful outcome may contribute a count to
asks-you. The feed shares CI opt-in, polling and closed reasons. It samples up to 50
updated open PRs per watched repository and returns at most 100 attention rows.

## What finished agents produced

GET /api/sources/v1/ci/ended → `{version:1,ended:Outcome}`.

Success data is `{rows,omitted}`. Each row has `{agentId,repo,number,title,url,
ci,mergeState,updatedAt}`. Join by agent ID to an Ended row. Merge state is
`merged|closed|draft|changes_requested|ready_to_merge|open|unknown`. Link the
latest PR associated with the branch, including a closed or merged PR if
GitHub still associates it with the branch. A branch without evidence of a
PR contributes no row. The feed shares CI opt-in, polling and closed reasons.

## Local machine load

GET /api/sources/v1/machine → `{version:1,machine:Outcome}`.

Success data is `{cpuLoadPercent,memoryPressurePercent,gpu}`. CPU is the
one-minute load average divided by logical core count, as a percentage that
may exceed 100. Memory is the percentage of memory in use under the platform's
available-memory calculation. An unavailable individual reading is null.
GPU is null without a usable local NVIDIA sample, or
`{utilizationPercent,memoryUsedBytes,memoryTotalBytes}`. With multiple NVIDIA
GPUs, utilization is the busiest GPU and memory is summed. No device names,
hostnames or paths are returned. The reader samples about every five seconds.
If it cannot read any measure, status is unavailable with reason
`cannot_read_machine`, the attempt time and null data. The same outcome is
included as `machine` in `nagi status --json`.


## Terminal summary

GET /api/sources/v1/status uses the same owner proof as the native clients and
reads cached observations. It returns `{version:1,agents,partial,ci,
claudeRemainingPercent,alerts,machine}`. Agents is null or
`{running,waitingOnYou,stuck}` from current readable sources. Partial indicates
missing or overlapping agent coverage. CI is `{state,failedRepos}`, with state
`disabled|ok|failed|unknown`. The Claude percentage comes from the lowest
fresh headline window of a single visible Claude account, or is null.
Alerts may contain `asks-you`, `stuck`, `ci-failed` and `low-limit`.
