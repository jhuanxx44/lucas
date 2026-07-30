# 支付链路降级处置手册

仅在证据满足对应条件时执行处置，不得把所有措施一次性套用。

## A. 上游响应变慢

条件：支付上游 p95 位于 3–5 秒，且 checkout 支付超时率超过 5%。

处置：

- `services/checkout-api/config.yaml` 中 `payment_client.timeout_seconds` 改为 6；
- `payment_client.max_retries` 改为 1，避免重试放大；
- 保持 `base_url`、checkout 并发数和其他下游配置不变。

验证命令：`verify checkout-payment --window 10m`

## B. 重复扣款防护

条件：日志出现 `duplicate charge suppressed=false`。

处置：把 `services/order-worker/config.yaml` 中 `idempotency_key_required` 改为 true；
保持队列名和 worker 并发数不变。

验证命令：`verify payment-idempotency --samples 200`

## C. 库存链路

只有库存错误率超过 2% 才允许修改 inventory-api。本事故若指标正常，禁止触碰库存配置。

回滚时按变更的反向依赖顺序：先回滚 order-worker，再回滚 checkout-api。
