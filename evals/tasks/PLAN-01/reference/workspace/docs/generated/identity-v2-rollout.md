# Identity V2 rollout

## Deploy

1. auth-gateway — gate: `identity-v2 healthcheck`
2. billing-worker — gate: `billing reconciliation`
3. notification-api — gate: `notification canary`

Stop immediately when a gate fails.

## Rollback

1. notification-api
2. billing-worker
3. auth-gateway
