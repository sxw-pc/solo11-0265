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

`python -m telemetrycourt archive --db demo.sqlite --fixture fixtures/archive_normal.json` 汇总当前可信观测的半开时间桶。

`python -m telemetrycourt egress --db demo.sqlite --fixture fixtures/egress_normal.json` 为同租户滚动字节额度内选择导出包并记录预留。

`python -m telemetrycourt histogram --db demo.sqlite --fixture fixtures/histogram_normal.json` 使用归档的样本身份和合成测量值生成按时间桶的直方图。

`python -m telemetrycourt probe-review --fixture fixtures/probe_arithmetic_normal.json` 回放定宽寄存器（[-7,7]，每次 add/subtract 先算真值再限幅）并据 limit 给出 open_review/normal。

`probe-formula` 为数值合同签发可在采集端直接运行的固定程序，全部验收结论都由 instrument_vm 的真实执行产生，不返回期望结果表：

```sh
python -m telemetrycourt probe-formula --fixture fixtures/probe_contract_legacy.json
python -m telemetrycourt probe-formula --fixture fixtures/probe_contract_raw.json --certificate 证书.json --reading fixtures/probe_reading_in_relation.json
```

合同分两类：`legacy_clip` 的命名限幅点（如历史读数 a+b）必须原样可核，限幅只能发生在该步骤，跨点重排无法表示该点即拒签；`raw_exact` 要求在由小整数界、关系（如 c>=b）和成组约束（组间不混搭）描述的完整合法域上零限幅、结果等于精确值，能借关系证明安全即签发，并标注独立宽域会否误判不可签。无固定程序满足时退出码 2，交付可经 `verify_artifact` 实跑复核的失败原件，列明越最终寄存器的精确值和每个首组的合法饱和见证。运行时 `run_certified` 把程序、关系域和阈值绑在同一张证书上；读数不满足已签关系时退出码 3、单独留置复核，不与旧证书凑成复核单。上限五个输入、两个命名限幅点，仅使用原有读入、加、减原语，无分支、无常量合成。
