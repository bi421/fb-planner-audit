- [ ] Verify/repair `ActionableCoachmark` runtime error separately (Chrome extension scripts).
- [x] QPAY + PRECHECK integration: add quota-aware precheck that skips scanning when quota exhausted and records usage to SQLite.
- [x] After `core/qpay.py` activates a subscription, return updated quota (precheck will enforce it on future requests).
- [x] Create `core/policy_updater.py` for weekly policy extraction and auto-update of `data/risky_words.json`.
- [x] Wire `policy_updater.update()` into `run.py` with `schedule.every().monday.do(update)`.
- [x] Run a quick python import check for the whole app entry (`python -c "import run"`).

