# SALES KIT - Robinhood Chain Safety Scanner

## The pitch in one line

Robinhood Chain has the traders, the volume, and the honeypots. It does not have a simple safety scanner. Now it does: paste a contract, get CLEAR / CAUTION / BLOCKED in seconds, free.

## Who it is for

- Robinhood Chain memecoin / launchpad traders (hood.fun, PONS, Pools.trade flow) who ape new contracts daily.
- Small trading groups and callers who share CAs and get blamed when a call is a honeypot.
- New Robinhood Wallet users arriving from the stock app who have never checked a contract in their life.

## Pricing

| Tier | Price | What they get |
|---|---|---|
| Free | $0 | Basic scan: chainId, code exists/size, proxy, Blockscout verification, token identity, owner, verdict with reasons |
| Pro | $9/month | Unlimited scans, new-pool watch + alerts, scan history, priority RPC, Telegram bot access |

Anchor line: "One honeypot costs you the whole bag. Pro costs $9."

## Where to sell it (first 2 weeks)

1. **Robinhood Chain trader groups (Telegram / Discord / X)**
   - Do not spam links. Answer "is this safe?" posts with a real scan screenshot + verdict, then the link. Receipts first.
   - Target groups already trading hood.fun / PONS launches where CAs fly every few minutes.
2. **Callers and group admins**
   - Offer: "Run every CA through the scanner before you call it. Free. Your members stop blaming you for honeypots you could have flagged." Admins are distribution.
3. **X / Farcaster content (Alpha Toolkit tie-in)**
   - Daily format: "Scanned today's most-shared Robinhood CA: verdict CAUTION, unverified + upgradeable proxy. Here's what that means." One real scan per post, screenshots, no invented tokens.
   - Thread angle: "Robinhood Chain passed Base in users. It still has no safety layer. I built one from my phone in Lagos."
4. **Launchpads**
   - Pitch hood.fun / PONS-style launchpads: a "Scan this token" badge/link per launch. Free for them, every launch page becomes your funnel.

## Copy you can paste

**Short post:**
> New Robinhood Chain token? Don't ape blind.
> Paste the CA, get CLEAR / CAUTION / BLOCKED + the reasons: verified or not, proxy or not, owner, code.
> Free scan: [link]
> It won't fake a honeypot verdict for you, and neither should any scanner.

**Group reply (when someone drops a CA):**
> Ran it through the scanner: [VERDICT] - [top 2 reasons]. Full report: [link]. DYOR, but don't skip the basic checks.

**Pro upsell (in the UI, after a free scan):**
> You scanned 3 contracts today. Active traders scan 30+ a week.
> Pro ($9/mo): unlimited scans, new-pool alerts, history, Telegram bot.
> One avoided honeypot pays for years of Pro.

## Objection handling

- **"Is CLEAR a guarantee?"** No, and say so loud. CLEAR = nothing this scanner checks tripped. Not an audit. The honesty is the brand - it is why Preflight worked on BSC.
- **"Does it detect honeypots?"** Not proven by a bytecode scan, and we do not fake it. We flag the traps around honeypots (unverified, proxy, owner control) and tell you to test a small buy and sell. A scanner that claims a clean honeypot verdict from bytecode alone is lying to you.
- **"Why not just use Blockscout?"** Blockscout is one of our checks. The scanner assembles chainId + code + proxy + verification + identity + owner into one verdict in 10 seconds, on your phone, no explorer digging.
- **"Why pay, it's free on other chains?"** Other chains have scanners. Robinhood did not. Pro pays for the watch/alerts/history, not the basic safety check - that stays free on purpose.

## Launch checklist

- [ ] Deploy `server.py` behind a public URL (or keep as local + Telegram bot first if hosting is a blocker - do not fake a live URL).
- [ ] Post scan #1: a real Robinhood CA, screenshot, verdict, reasons.
- [ ] Drop helpful scans (not links) in 3 trader groups, 2 days running.
- [ ] Offer 5 group admins a free Pro month for pinning the scanner link.
- [ ] Track: scans/day, repeat scanners, Pro conversions. Kill or double down at day 14 based on real numbers only.

## Guardrails

- Never claim a token is safe. Never claim sellability is proven.
- Never scan-and-shill your own bag without disclosing it.
- Every public scan screenshot must be a real run. No mock verdicts in marketing.
