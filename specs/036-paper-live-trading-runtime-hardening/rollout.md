# Rollout and Review: Runtime Hardening

## Paper Deployment Acceptance Checklist
- [ ] Runtime mode set to `paper`
- [ ] Redis signal connection verified
- [ ] Hard risk limits (size, loss) configured and verified
- [ ] Audit trail logging to disk enabled
- [ ] Restart recovery verified (seen_signals persistence)

## Limited-Live Rollout Checklist
- [ ] Execution mode set to `live_limited`
- [ ] Exchange API keys with limited permissions (trading only)
- [ ] Risk policy: max position size reduced to minimum
- [ ] Kill switch access verified
- [ ] Manual supervision for first 24h of signals

## External Review Evidence
- [x] Replay-safe signal safety policy implemented
- [x] Hard risk engine for size and loss enforcement
- [x] Durable execution state across restarts
- [x] Comprehensive execution audit trail
