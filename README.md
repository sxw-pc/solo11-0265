# 遥测覆盖可信裁定所

面向平台值班与可观测团队的离线业务模拟。Python 3.11+ 标准库和 SQLite 即可运行；样例均为合成对象、代理与采样，不连接真实集群或监控服务。

三个业务入口分别处理覆盖契约、采集证据和盲区处置。覆盖要求记录对象 UID、信号、最少独立来源和最大采样间隔。代理租约把样本绑定对象 UID、代理身份、来源和租期；漂移证据可隔离已采样事实，并重新打开依赖这些事实关闭的盲区。盲区案保留当时契约阈值，维护豁免必须有值班与所有者两人审批，恢复还需要连续覆盖和独立见证。

在仓库根目录运行：

```sh
python -m telemetrycourt demo --db demo.sqlite
python -m telemetrycourt replay --db demo.sqlite
python -m unittest discover -s tests -v
```

单独调用：`python -m telemetrycourt cover --db state.sqlite --fixture fixtures/cover_normal.json`，`agent` 和 `blind` 类推。六份正常/失败样例按 cover-normal、agent-normal、blind-normal、cover-failure、agent-failure、blind-failure 的顺序共享数据库执行；`demo` 即为该顺序。`report` 输出不可变事件；`replay` 在空数据库重放并逐业务表核对。主要结论包括覆盖可信、盲区升级、维护抑制、采样隔离、恢复不充分和关单。

`python -m telemetrycourt spool --db state.sqlite --fixture fixtures/spool_normal.json` 为当前可信样本预留离线导出字节。先用 cover/agent 正常 fixture 填充同一个库。

`python -m telemetrycourt notifications --db demo.sqlite --fixture fixtures/notifications_normal.json` 按已有盲区标签和通道额度模拟通知。
