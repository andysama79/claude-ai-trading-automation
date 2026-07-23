# Tech spec: static IP for Kite Connect order placement

## Status

Needed.
Confirmed against current Zerodha documentation on 2026-07-23.
Scoped separately from issue #4 (auth.py), which is closed.

## Problem

Zerodha requires a static IP for all API-based order placement, as an SEBI algo-trading compliance rule.
The requirement took effect April 1, 2026.
That date has already passed.
This service currently runs (or is deployed) without a static IP, so it is out of compliance for live order placement right now.

## What the requirement actually covers

Source: [Zerodha support article, "Static IP"](https://support.zerodha.com/category/trading-and-markets/general-kite/kite-api/articles/static-ip), confirmed via WebFetch on 2026-07-23.

- Only order-placement APIs need the static IP.
  The WebSocket market data stream and other APIs, such as orderbook and positions, can continue to be accessed from any IP.
- It is mandatory, not optional, for order placement.
- Configured at the Kite Connect developer account level, not per app.
  Profile → IP Whitelist → enter IP → Update.
- Up to two IPs can be whitelisted (one required, one optional).
- Only one change is allowed per calendar week.
  Get it right the first time; there is no quick fix for a mistyped IP.
- Families sharing one IP across accounts use a single developer account with one app per family member, each app listing the relevant client IDs, plus a declaration that the IP is used only by the account holder and immediate family.
- The article does not state whether IPv6 is accepted alongside IPv4.
  Treat this as IPv4-only until Zerodha's docs say otherwise, and confirm the destination API host resolves over IPv4 from wherever we host.

This matches and extends the SEBI circular background from earlier research (SEBI/HO/MIRSD/MIRSD-PoD/P/CIR/2025/0000013, deadline later fixed at April 1, 2026 via SEBI/HO/MIRSD/MIRSD-PoD/P/CIR/2025/132).

Sources:
- [Static IP — Zerodha support](https://support.zerodha.com/category/trading-and-markets/general-kite/kite-api/articles/static-ip)
- [Preparing to comply with SEBI's retail algo rules: static IP, rate limits, order types — Kite Connect forum](https://kite.trade/forum/discussion/15912/preparing-to-comply-with-sebis-retail-algo-rules-static-ip-ratelimits-order-types)
- [Notes on the NSE circular prescribing operating procedures for API usage — Kite Connect forum](https://kite.trade/forum/discussion/15350/notes-on-the-nse-circular-prescribing-operating-procedures-for-api-usage)

## Why this can't be solved without infra work

Nothing in this repo controls outbound IP today.
`trader/brokers/kite.py` calls `kiteconnect`'s HTTP client directly; whatever machine runs the process uses whatever IP that machine's network egress happens to have.
On a laptop, home broadband, or any host without a fixed IP, that address changes on reconnect, DHCP renewal, or ISP-level NAT rotation, so it can never stay whitelisted.
This is an infrastructure problem, not a code problem, and needs a host (or proxy) that guarantees a fixed outbound IP.

## Options considered

| Option | Static egress IP? | Cost | Notes |
|---|---|---|---|
| **Fly.io dedicated egress IP** (recommended) | Yes, app-scoped, per-region | ~$3.60/month | Already the recommended deploy target in `docs/deploy/README.md`. No migration off Fly.io needed, only an add-on. |
| AWS (EC2 + Elastic IP, or NAT Gateway) | Yes | ~$3.50-5/month EC2, more with NAT Gateway | Was the original instinct in the prior discussion. Works, but requires standing up new infra from scratch; no advantage over Fly.io here. |
| GCP e2-micro free tier | Only with a reserved external IP (small extra cost once attached to a running instance) | Free VM + ~$1-3/month for the reserved IP | Viable, already documented as an option, but not clearly cheaper or simpler than the Fly.io add-on. |
| Heroku / Railway / Render | No | - | Dynamic egress IPs by design, ruled out. |
| Third-party static-IP proxy (QuotaGuard, Fixie) | Yes, via HTTP(S) proxy | ~$10+/month | Adds an extra hop and a second vendor dependency for something Fly.io already covers natively. Not needed. |

**Recommendation: use Fly.io's dedicated egress IP add-on.**
It keeps the existing recommended deploy path in `docs/deploy/README.md` intact and avoids standing up or migrating to new infrastructure for what is, at its core, a single IP address.

## Implementation

1. On the Fly.io app already used for this service (`trader-YOUR_NAME` per `docs/deploy/README.md`), allocate a dedicated egress IP:
   ```bash
   fly ips allocate-v4 --app trader-YOUR_NAME
   ```
   (Exact command per current Fly docs at deploy time; Fly's egress IP feature is app + region scoped, so pin the app to a single region if not already.)
2. Confirm the assigned IP with `fly ips list`.
3. Log into the Kite Connect developer console, go to Profile → IP Whitelist, and enter that IP.
   This uses the one-change-per-week allowance, so verify the IP is correct before saving.
4. Redeploy and place a real order-path smoke test (small quantity, market hours) to confirm Kite accepts requests from the new IP.
5. Update `docs/deploy/README.md` with this step under the Fly.io section, so it isn't missed on a fresh deploy.

## Constraints to carry into any future infra change

- One whitelist change per calendar week means any redeploy that changes the egress IP (for example, moving to a new Fly.io app, or switching region) needs to be planned a week ahead, not done reactively.
- The IP is whitelisted at the developer-account level, so it covers all apps/client IDs under that account already; no per-symbol or per-strategy config needed.
- If a second host is ever added (e.g., a paper-trading instance, per `docs/ROADMAP-MVP.md`'s go-live readiness phase) that also places live orders, it needs its own whitelisted IP within the same two-IP limit, or a shared static IP.

## Out of scope here

- Issue #4 (auth.py, daily re-auth): resolved separately in PR #10, closed.
- TOTP-based fully automated daily re-auth: already implemented (`KiteBroker._auth_totp`), unaffected by this change.
- Any change to `trader/brokers/kite.py` itself: this is purely a deploy/infra change, no code in this repo needs to move.

## Epic: rollout plan and corner cases

This is the first infrastructure migration for this project, tracked as epic #12.
The single-IP allocation above is the easy part.
The corner cases below are why it is an epic and not a one-off task.

### Corner cases identified

1. **Region/multi-instance drift.** Fly.io's dedicated egress IP is scoped to one app in one region. If the app ever scales to a second region, or gets recreated under a new app name, the new instance gets a different IP that is not yet whitelisted, and order placement silently starts failing.
2. **IPv4 vs IPv6 egress.** Zerodha's docs do not say whether IPv6 is accepted. If the runtime prefers IPv6 for outbound requests when both are available, it can bypass the whitelisted IPv4 address entirely without raising an obvious error. Needs an explicit check of how `kiteconnect`'s HTTP client (and Fly.io's network stack) resolves and dials the Kite API host.
3. **One change per calendar week.** Any process that touches the egress IP (redeploy to a new app, region change, IP reallocation) can strand the service for up to a week if done without planning. This rules out any deploy step that might implicitly change the IP.
4. **CI vs CD blast radius.** The CI workflow from #13 only runs tests. A CD step added on top of it must never run anything equivalent to `fly apps destroy` + recreate, or an unpinned `fly launch`, since either can silently rotate the egress IP. The CD step's job is to redeploy the *existing* app in place.
5. **TOTP auth traffic.** Order placement is the only endpoint Zerodha documents as requiring the static IP, but `KiteBroker._auth_totp()` also calls Kite Connect endpoints from the same process. Confirm the daily TOTP re-auth flow keeps working from the whitelisted IP too, since it runs on the same egress path.
6. **Local development.** Engineers still need to run and test the service without a static IP (unit tests, paper-mode runs against non-order-placement endpoints). The migration must not make local dev depend on the whitelisted IP.
7. **Silent failure mode.** If Kite rejects an order because the request came from a non-whitelisted IP, that must show up as a loud, specific error/alert, not a generic order-placement failure indistinguishable from a margin or symbol error.
8. **Future second instance.** Only two IPs can ever be whitelisted account-wide. Any future HA or paper-trading instance that also places live orders needs to fit inside that cap. Out of scope for the current single-instance setup, but the constraint needs to be written down now so it isn't rediscovered mid-incident later.

### Subtasks

Filed as separate issues under epic #12, in rollout order:

1. Allocate and pin the Fly.io dedicated egress IP (single app, single region) — corner case 1.
2. Verify the egress path to `api.kite.trade` is IPv4-only, and force IPv4 if the runtime could otherwise prefer IPv6 — corner case 2.
3. Whitelist the IP in the Kite Connect developer console, then smoke-test both order placement and the TOTP re-auth flow from the deployed instance — corner cases 3, 5.
4. Extend the CI workflow (#13) into a CD step that redeploys the existing Fly.io app in place, with an explicit guard against app/region recreation — corner case 4.
5. Add alerting that distinguishes an IP-whitelist order rejection from other order failures — corner case 7.
6. Update `docs/deploy/README.md` and `CLAUDE.md` with the static-IP setup step and the one-change-per-week caveat — keeps corner case 6 (local dev) and corner case 8 (future second instance) documented for whoever picks up HA later.
