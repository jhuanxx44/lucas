# Identity API V2 迁移要求

所有仍在运行且 `identity_api.version: 1` 的服务必须统一改为：

```yaml
identity_api:
  version: 2
  endpoint: /v2/identity
  timeout_seconds: 8
  headers:
    X-Identity-Version: "2"
```

迁移时必须保留服务原有的副本数、队列名和其他业务配置。已经使用 V2 的服务无需改动，
`active: false` 的服务只保留历史状态，不参与本轮发布。

发布必须遵循服务的 `depends_on`：依赖方先部署，被依赖它的服务后部署。每阶段门槛如下：

- auth-gateway：`identity-v2 healthcheck` 通过。
- billing-worker：`billing reconciliation` 通过。
- notification-api：`notification canary` 通过。

任何阶段失败时停止继续发布，并按已经部署服务的逆序回滚。
