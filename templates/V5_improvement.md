# Nano Lab Stock Check System - 架构升级与 UI 重构方案 (V5)

本文档定义了 Nano Lab 试剂库存检查系统从 V4 升级到 V5 的核心逻辑重构方案。重点解决数据展示的割裂感、硬编码问题、用户命名不规范问题，以及表格 UI 的层级混乱问题。

## I. 核心逻辑重构：统一看板与权限分离 (Unified Dashboard)

**目标**：废弃原有的“双表格”设计（当前表 + 历史表），将其融合成一个全局的“全景看板”。

### 1. 动态数据抓取逻辑 (Backend - `app.py`)
* **消除特定日期限制**：目前系统仅查询 `check_date = 今天` 的数据。重构后，系统将遍历所有数据表，抓取**每一个物品在每一个组别下的“历史最新记录”**（`MAX(check_date)`），无视该记录是昨天还是上个月生成的。
* **移除冗余代码**：彻底删除 `app.py` 中用于生成 `prev_checks`（上一轮值组数据）的查询逻辑。
* **彻底实现 Config-Driven（配置驱动）**：
    * 移除前端对组数 `5` 的硬编码限制（改为动态长度 `groups|length`）。
    * 将 `Dr.Lee/Zhijun` 的特权判断从硬编码改为读取 `teams_config.json` 中的特权标签（例如 `"is_admin_for_tips": true`），以便未来人员更迭时无需修改 Python 代码。

### 2. 前端展示与权限控制 (Frontend - `dashboard.html`)
* **唯一表格**：删除 `` 相关的完整 HTML 代码块。
* **轮值组（Write 状态）**：当且仅当今天是某组的“库存检查日”时，该组的列才会渲染为 `<input>` 输入框，允许录入数据。
* **非轮值组（Read-Only 状态）**：未到检查日的组别，其列将变为纯展示模式。
    * **显示内容**：显示该组最后一次登记的库存数量。
    * **时间戳标明**：在数量下方用浅色小字标注最后一次更新的日期（例如：`Last checked: 2026-02-26`）。

---

## II. 管理员新功能：显示名称一键同步 (Admin Display Name Sync)

**问题背景**：实验室成员在注册时可能会随意填写 `Display Name`，导致名称与实际的 `Group Name`（如 Junhyun/Thuan）不一致，给管理带来混乱。

**解决方案**：
1.  **后端路由 (`app.py`)**：新增一个管理员专属路由 `/admin/sync_name/<int:user_id>`。当调用该路由时，系统会自动将该用户的 `display_name` 覆盖为其绑定的 `group_name`。
2.  **前端操作 (`admin.html`)**：在管理员面板的用户列表操作栏（Actions）中，紧挨着“Edit”按钮添加一个 **"Sync Name"** 按钮。
    * *逻辑表现*：点击后，如果用户的显示名是 "ZHAO ZHIJUN" 但组名是 "Dr.Lee/Zhijun"，系统会强制将显示名更新为 "Dr.Lee/Zhijun"，保持高度一致。

---

## III. 前端表格 UI 升级：多级表头架构 (Table UI Redesign)

**问题背景**：当前的表格表头是扁平的（Flat），`#`, `Item`, `Minimum` 与 `Team A`, `Team B` 处于同一层级，视觉上缺乏逻辑从属关系，显得非常怪异。

**解决方案**：使用 HTML 的 `rowspan` 和 `colspan` 属性构建“双层表头（Two-tier headers）”，明确界定【物品信息区】、【各组库存区】和【订单状态区】。

**预期 UI 结构**：
```text
|   |         |         |          Group (Teams)          |       Order Pipeline       |
| # |  Item   | Minimum |---------------------------------|----------------------------|
|   |         |         | Team A | Team B | Team C | ...  | Order | Request | Result |