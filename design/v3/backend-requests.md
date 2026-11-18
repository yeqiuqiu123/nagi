# Backend requests from the v3 design

None of these blocks v3: the panel is built on the API as it is (`design/sources-api.md`, `design/api-contract.md`) and degrades as described. They are for whoever owns the reader next.

## 1. An explicit identity for "the same account" across sources

**Today.** The owner asked for one dial per account window, with chips for the sources that read it. The view model merges two readings when provider, window label and reset instant (to the minute) match: the key the reader already uses so a low-limit alert is never delivered twice.

**The gap.** `design/sources-api.md` ("T3 overlap and alerts") says that key is for alert dedup only and that T3's `instanceId` is not a proven account id. Two different accounts whose weekly windows happen to reset in the same minute would be drawn as one dial. It is unlikely, and the dial's detail names every source that read it, but it is an inference.

**Ask.** A stable, non-secret `accountKey` on each limits account (the HMAC the direct Codex reader already derives would do, if T3-read accounts can carry the same one), or an explicit `sameAs` between a T3 account and a direct one. The panel would then merge on the key and stop inferring.

## 2. A window's own length

**Today.** The tick on a dial is the time left in the window. The panel knows the length only from `kind`: `five_hour`, `weekly`, and `monthly` as one calendar month back from `resetsAt`. A window of kind `other` gets no tick.

**Ask.** `windowMinutes` (or `startsAt`) on each window, as T3 already reports `windowDurationMins`. Every window would get an honest tick, and a monthly cycle that isn't a calendar month would be right.

## 3. When a question was asked

**Today.** `asks you · 4m` counts from the row's last activity, because the contract carries no request time.

**Ask.** `waitingOnYou.since`. The header and the row would then say how long you have kept it waiting, not how long it has been quiet.

## 4. Per-source ended counts that can be summed

**Today.** The one Ended line sums each source's own `counts.ended`, leaving out a source whose rows may repeat another's (Cursor beside a local T3), as the running count already does.

**Ask.** Nothing new if that rule is right. If the reader can mark a thread as the same thread seen by two sources, the sum could include every source.

## Not requested

- Activity history for a run-time chart. A duration has no natural maximum to draw against; the number is the better mark, and history is the dashboard the bar refuses.
- Any write or control endpoint. Nagi stays read-only.
