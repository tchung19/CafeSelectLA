# CafeSelect — Known Gaps & Future Work

## Frontend

- ~~**Show cafe count by neighborhood**~~ — done. `/neighborhoods` now returns `{name, count}` and pills show the count inline.

## Search & Filtering

- **"Open tomorrow" queries not handled** — if a user asks on Saturday evening for something "open tomorrow morning", we don't resolve the target day. `open_now` and `open_after` only operate against today's hours column. Fix: extend the query parser to extract a target day offset and pass it to `run_search`.
