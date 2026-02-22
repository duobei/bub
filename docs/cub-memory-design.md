# Cub 记忆方案设计

> 基于 Bub 核心设计理念："历史可以丢"、"构造而非继承"、"按需读取"

## 核心理念

```
任务出现 → 构造上下文 → 完成任务 → 结束
下一轮重新开始
```

### 与传统方案的对比

| 维度 | 传统 Memory/上下文管理 | Cub 记忆方案 |
|------|----------------------|--------------|
| 状态观 | 必须维护延续状态 | 状态是可选资源 |
| 历史观 | 默认继承历史 | 历史可丢，按需查询 |
| 上下文 | 递增函数 | 构造函数 |
| 会话 | 身份边界 | 任务边界 |
| 复杂度 | 缓存→提取→合并→压缩→分叉 | 探索+选择 |

---

## 架构设计

### 1. 记忆分层模型

```
┌─────────────────────────────────────────────────────────┐
│                    构造层 (On-demand)                     │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐    │
│  │  探索   │→│  选择   │→│  构建   │→│  验证   │    │
│  └─────────┘  └─────────┘  └─────────┘  └─────────┘    │
├─────────────────────────────────────────────────────────┤
│                    存储层 (Append-only)                   │
│  ┌─────────────────────────────────────────────────┐   │
│  │                    Tape                          │   │
│  │  [Entry] [Entry] [Entry] [Anchor] [Entry] ...   │   │
│  └─────────────────────────────────────────────────┘   │
├─────────────────────────────────────────────────────────┤
│                    索引层 (Optional)                      │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐            │
│  │ 锚点索引 │  │ 语义索引 │  │ 关键词索引│            │
│  └──────────┘  └──────────┘  └──────────┘            │
└─────────────────────────────────────────────────────────┘
```

### 2. 核心组件

#### 2.1 Tape (打孔纸带)

- **只读存储**：所有记忆以 append-only 方式写入
- **结构化Entry**：每条记录包含 `id`, `kind`, `payload`, `meta`
- **锚点(Anchor)**：标记任务阶段的里程碑

```python
# Entry 类型
- message: 对话消息
- tool_call: 工具调用
- tool_result: 工具结果
- anchor: 任务里程碑 (handoff)
- event: 业务事件
```

#### 2.2 Context Constructor (上下文构造器)

不是将所有历史塞入窗口，而是：

```python
class ContextConstructor:
    """按需构造上下文"""

    def construct_for_task(self, task: str, tape: Tape) -> list[Message]:
        # 1. 探索：查询相关历史
        relevant = self.explore(task, tape)

        # 2. 选择：丢弃无关内容
        selected = self.select(task, relevant)

        # 3. 构建：构造最小充分上下文
        return self.build(selected)

    def explore(self, task: str, tape: Tape) -> list[Entry]:
        """探索可能相关的记忆"""
        # 搜索锚点
        anchors = tape.anchors()

        # 语义搜索（如需要）
        if self.has_rag:
            return tape.search(task)

        # 或返回最近 N 条
        return tape.recent(limit=50)

    def select(self, task: str, candidates: list[Entry]) -> list[Entry]:
        """选择最小充分材料"""
        # 模型自己决定哪些相关
        # 或用规则过滤
        return self.model_filter(task, candidates)
```

#### 2.3 Anchor System (锚点系统)

标记任务阶段的转换：

```python
# 锚点类型
- task/start: 新任务开始
- task/progress: 任务进展
- task/done: 任务完成
- task/fail: 任务失败
- session/start: 会话开始
```

### 3. 操作接口

#### 3.1 基础操作

```python
# 写操作
tape.append(entry)           # 追加记录
tape.handoff(name, state)   # 创建锚点

# 读操作
tape.read()                  # 读取全部
tape.recent(limit)          # 最近 N 条
tape.anchors()               # 所有锚点
tape.search(query)           # 搜索
tape.between(start, end)     # 锚点间内容
tape.after(anchor)           # 锚点之后内容
```

#### 3.2 上下文构造

```python
# 自动构造（默认行为）
context = tape.context_for("帮我修复 Linux 桌面")

# 手动构造（高级用法）
with tape.fork() as fork:
    # 在独立上下文中工作
    context = fork.context()
```

---

## 场景示例

### 场景 1: 群聊中的多任务

```
群聊中同时存在多个任务：
- A 问 "如何修复 Linux 桌面"
- B 问 "今晚吃什么"
- C 问 "帮我写个脚本"

传统方案：需要复杂的上下文隔离
Cub 方案：每个任务独立构造上下文
```

```python
# 任务 A 的上下文构造
ctx_a = tape.context_for("修复 Linux 桌面")
# 可能只包含：
# - 最近 10 条相关讨论
# - 之前的锚点 "linux-task/start"

# 任务 B 的上下文构造
ctx_b = tape.context_for("今晚吃什么")
# 可能只包含：
# - 最近 5 条对话
# - 完全不包含任务 A 的内容
```

### 场景 2: 长任务中的阶段转换

```
用户让 Agent 做一个复杂任务：
1. 分析需求
2. 编写代码
3. 测试
4. 部署

每个阶段用锚点标记：
```

```python
# 阶段 1
tape.handoff("phase:analysis", state={"goal": "分析需求"})
# ... 分析过程 ...

# 阶段 2
tape.handoff("phase:implementation", state={"goal": "编写代码"})
# ... 编码过程 ...

# 上下文恢复
# 如果需要回到某个阶段：
tape.after("phase:analysis")  # 只获取分析后的内容
```

### 场景 3: 上下文溢出处理

```
当上下文即将溢出时：
传统方案：压缩、摘要、截断
Cub 方案：丢弃重建
```

```python
class OverflowHandler:
    def handle(self, tape: Tape, limit: int) -> Context:
        # 1. 检查是否需要处理
        if tape.size() < limit:
            return tape.full_context()

        # 2. 找到最近的锚点
        last_anchor = tape.last_anchor()

        # 3. 只保留锚点之后的内容
        # 或者：创建新锚点，重新开始
        tape.handoff("context:overflow", state={"reason": "length"})

        # 4. 探索历史，选择相关
        return self.construct_for_current_task(tape)
```

---

## 与传统方案的对比

### vs Session/会话

| Session | Cub |
|---------|-----|
| 会话是身份边界 | 会话是任务边界 |
| 跨会话需要复制/继承 | 跨任务按需查询 |
| 状态必须延续 | 状态可以重建 |

### vs Memory

| Memory | Cub |
|--------|-----|
| 提取事实存储 | 保留原始记录 |
| 追求一致性 | 接受不完美 |
| 作为旁路，可能失效 | 作为主要存储 |
| 维护成本高 | 简单可靠 |

### vs RAG

| RAG | Cub |
|-----|-----|
| 外部知识库 | 内置记忆 |
| 检索作为增强 | 记忆是素材库 |
| 复杂的索引维护 | 简单的 anchor 索引 |

---

## 实现优先级

### P0 - 核心功能 (已完成 ✅)

- [x] Append-only Tape 存储
- [x] Anchor 锚点系统
- [x] 基础读写 API
- [x] 搜索功能

### P1 - 重要增强 (已完成 ✅)

- [x] Context Constructor（按需构造）- `recent()`, `context_for()`, `context_summary()`
- [x] 多任务/多会话隔离 - Fork/Merge 支持
- [x] 新增工具：
  - `tape.context` - 为特定任务构造上下文
  - `tape.context_summary` - 查看上下文状态摘要

### P2 - 高级特性

- [ ] 语义搜索（可选 RAG）
- [ ] 自动锚点建议
- [ ] 上下文溢出处理（基于"历史可丢"理念）

---

## 设计原则总结

1. **构造而非继承**：每个任务从相关材料构造上下文
2. **历史可丢**：不是必须背在身上的包袱
3. **按需读取**：Tape 是素材库，不是生命线
4. **更少假设**：不预设任务必须延续
5. **简单可靠**：机制越少，越不容易出错

> "所谓更聪明，不是引入更多机制。而是减少假设。"
> — Luca Zhan
