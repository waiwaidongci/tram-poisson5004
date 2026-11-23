# 002 停测单与结论失效

- `datasets` 新增 `outages` JSON 列保存信号台停测单，批次指纹同时覆盖观测行与停测记录。
- 已有数据库执行显式迁移：`ALTER TABLE datasets ADD COLUMN outages JSON NULL;` 旧批次按无停测记录处理。
- 同名批次导入新数据（观测或停测单有变化）即产生新指纹版本；旧批次上的运行结论立即失效，禁止导出与复核，重算完成后才出新排班依据。
