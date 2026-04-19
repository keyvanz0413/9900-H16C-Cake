# Unsubscribe Tool Merge Plan

这份文档用于指导 `unsubscribe` 工具链的下一轮简化重构。

当前目标不是立刻改所有行为，而是先统一设计，明确：

- 哪几个工具应该合并
- 合并后的新工具输入输出长什么样
- `unsubscribe_discovery` 和 `unsubscribe_execute` 应该如何改
- 哪些旧工具可以保留兼容，哪些后续可以删除

---

## 1. 当前问题

目前退订链路里，下面这几个工具在 skill 视角下过于零碎：

- `get_email_headers`
- `parse_list_unsubscribe_header`
- `classify_unsubscribe_method`
- `extract_unsubscribe_links_from_email`

它们的问题是：

- 调用粒度太碎，一个“判断这封邮件怎么退订”的动作被拆成了很多步
- skill 里要自己串很多中间 JSON，读起来很重
- `unsubscribe_discovery` 和 `unsubscribe_execute` 都在重复类似流程
- `extract_unsubscribe_links_from_email` 本质上只服务 `website / manual link` 形式，但现在暴露成了单独工具步骤
- 对后续执行层来说，真正想要的不是很多中间态，而是“这封邮件有哪些退订选项，以及对应执行参数是什么”

换句话说，当前链路更像“底层实现视角”，不是“skill / workflow 使用视角”。

---

## 2. 目标

把下面这些能力合并进一个新的只读分析工具：

- 读取 header
- 解析 `List-Unsubscribe`
- 分类退订方式
- 解析 `mailto`，直接产出可发送字段
- 在需要时提取 `website / manual link`

新工具直接输出“可执行准备结果”的统一 JSON。

这个 JSON 要能直接服务三种后续路径：

1. `one_click`
2. `mailto`
3. `website / manual link`

也就是：

- 对 `one_click`，直接给出可以传给执行器的 URL
- 对 `mailto`，直接给出可发送的 `to / subject / body`
- 对 `website`，直接给出可展示给用户的手动退订链接

此外，这个新工具必须支持一次接收多个 `email_id`。

这样 skill 不需要再自己拼装中间态。

---

## 3. 设计原则

### 3.1 新工具只做分析，不执行退订

新工具本身不执行退订动作，只负责：

- 读取 Gmail metadata
- 分析退订能力
- 在需要时补齐 manual links
- 产出标准化 JSON

它不应该：

- 发 POST
- 发邮件
- 自动访问网页

### 3.2 Website 形式也由新工具统一产出

原来的 `extract_unsubscribe_links_from_email` 不再作为 skill 主链的单独一步暴露。

新的理解是：

- `extract_unsubscribe_links_from_email` 只是为 `website / manual link` 形式服务
- 所以它应该被折叠进新的统一分析工具内部
- 对 skill 来说，不需要再关心“是否要额外从正文提链接”

也就是说，从 skill 视角看：

- 所有退订能力分析都来自一个统一工具
- `website` 情况下，新工具直接把可用手动链接整理好输出

### 3.3 Skill 应看到“执行准备结果”，而不是原始 header 细节

skill 更关心的是：

- 这封邮件能不能退订
- 应该走哪种方式
- 如果走 `one_click`，下一步参数是什么
- 如果走 `mailto`，下一步参数是什么
- 如果只能网页退订，能给用户展示哪些手动链接

而不是自己重新解释原始 header。

---

## 4. 新工具建议

建议新增工具：

```python
get_unsubscribe_info(email_ids: list[str]) -> str
```

这是一个只读工具。

输入：

- `email_ids`: 必填，目标 Gmail message id 列表

要求：

- 支持一次分析多封邮件
- 可同时用于 discovery 和 execute
- execute 场景下即使只有一封，也统一传单元素列表

输出：

- 一个统一 JSON 字符串

这个新工具的语义是：

- 批量输入多个 `email_id`
- 批量输出一个统一 JSON
- 每个 `email_id` 对应 `items` 里的一个结果对象
- `mailto` 情况下，不再需要 skill 额外调用 `parse_mailto_url`
- 因为新工具已经直接把 `send_payload` 算好了
- 它返回的就是：
  - 退订分类结果
  - 后续真正执行退订所需要的信息

---

## 5. 新工具输出 JSON 规范

建议输出结构如下：

```json
{
  "items": [
    {
      "email_id": "18c123...",
      "unsubscribe": {
        "method": "one_click",
        "options": {
          "one_click": {
            "url": "https://example.com/unsub/abc",
            "request_payload": {
              "url": "https://example.com/unsub/abc"
            }
          },
          "mailto": {
            "url": "mailto:leave@example.com?subject=unsubscribe",
            "send_payload": {
              "to": "leave@example.com",
              "subject": "unsubscribe",
              "body": ""
            }
          },
          "website": {
            "url": "https://example.com/unsub/abc",
            "manual_links": [
              {
                "url": "https://example.com/unsub/abc",
                "label": "Open unsubscribe page",
                "source": "list_unsubscribe_header"
              }
            ]
          }
        }
      },
      "error": ""
    }
  ],
  "summary": {
    "requested_count": 1,
    "analyzed_count": 1,
    "error_count": 0
  },
  "error": ""
}
```

如果 `website` 场景下 header 不够用，而正文里能找到更明确的退订链接，则 `manual_links` 由正文提取结果补齐，例如：

```json
{
  "website": {
    "url": "",
    "manual_links": [
      {
        "url": "https://example.com/preferences/unsubscribe?id=abc",
        "label": "Unsubscribe",
        "source": "text/html"
      }
    ]
  }
}
```

### 5.2 批量输出示例

也就是说，它完全可以一次返回一个“批量 JSON”，例如：

```json
{
  "items": [
    {
      "email_id": "msg_1",
      "unsubscribe": {
        "method": "one_click",
        "options": {
          "one_click": {
            "url": "https://example.com/unsub/abc",
            "request_payload": {
              "url": "https://example.com/unsub/abc"
            }
          }
        }
      },
      "error": ""
    },
    {
      "email_id": "msg_2",
      "unsubscribe": {
        "method": "mailto",
        "options": {
          "mailto": {
            "url": "mailto:leave@example.com?subject=unsubscribe&body=please%20remove%20me",
            "send_payload": {
              "to": "leave@example.com",
              "subject": "unsubscribe",
              "body": "please remove me"
            }
          }
        }
      },
      "error": ""
    }
  ],
  "summary": {
    "requested_count": 2,
    "analyzed_count": 2,
    "error_count": 0
  },
  "error": ""
}
```

所以答案是：

- 可以批量输入多个 `email_id`
- 也可以批量产出一个 JSON
- skill 只需要遍历这个 JSON 的 `items`
- execute 场景下如果只处理一封，也仍然可以传 `[email_id]`
- 不存在的选项完全不写，不保留 `available: false` 这种占位字段

### 5.1 字段说明

#### 顶层

- `items`
  - 每个 `email_id` 对应一个分析结果

- `summary`
  - 批量分析摘要，例如请求数、成功数、错误数

- `error`
  - 顶层整体错误

#### 单项结果

- `email_id`
  - 当前分析的 message id

- `error`
  - 单封邮件分析失败原因

#### `unsubscribe`

- `method`
  - 最终主分类，取值建议：
    - `one_click`
    - `mailto`
    - `website`
    - `multiple`
    - `unknown`

- `options.one_click.request_payload`
  - 如果存在，给后续 `post_one_click_unsubscribe(...)` 的直接输入

- `options.mailto.send_payload`
  - 如果存在，给后续 `send(...)` 的直接输入
  - 这里意味着 `parse_mailto_url` 的结果已经被新工具内联出来

- `options.website.manual_links`
  - 如果是网页 / 手动退订，这里直接给可展示链接
  - 链接来源可能是：
    - `list_unsubscribe_header`
    - `text/html`
    - `text/plain`

---

## 6. 推荐实现范围

### 6.1 第一阶段

先把下面 4 个工具逻辑折叠到一个新工具里：

- `get_email_headers`
- `parse_list_unsubscribe_header`
- `classify_unsubscribe_method`
- `extract_unsubscribe_links_from_email`

并且在新工具内部顺手完成原来 `parse_mailto_url` 的解析工作，把 mailto 的发送参数也一起算出来。

也就是说，从 skill 视角看，真正的新读工具是：

- `get_unsubscribe_info`

然后执行工具只保留：

- `post_one_click_unsubscribe`
- `send`

### 6.2 第二阶段

如果第一阶段稳定，可以考虑：

- 从 skill 的 `used_tools` 里去掉 `parse_mailto_url`
- 不再让 skill 直接使用 `get_email_headers / parse_list_unsubscribe_header / classify_unsubscribe_method / extract_unsubscribe_links_from_email`

### 6.3 第三阶段

如果全链路稳定，再考虑是否彻底删除这些旧工具的公开注册：

- `get_email_headers`
- `parse_list_unsubscribe_header`
- `classify_unsubscribe_method`
- `parse_mailto_url`
- `extract_unsubscribe_links_from_email`

注意：

- 可以先保留底层 helper 函数
- 但不一定还需要继续对 agent 注册为公开工具

---

## 7. 对两个 Skill 的影响

### 7.1 `unsubscribe_discovery`

当前：

- `search_emails`
- `get_email_headers`
- `parse_list_unsubscribe_header`
- `classify_unsubscribe_method`

改造后建议：

- `search_emails`
- `get_unsubscribe_info`

新的 discovery 流程：

1. `search_emails(...)` 找候选邮件
2. 一次把候选 `email_id` 列表传给 `get_unsubscribe_info(email_ids=[...])`
3. 直接根据返回 JSON 汇总：
   - email_id
   - method
   - 已存在的执行信息
   - manual_links

这样 discovery 会明显更短，也更容易读。

### 7.2 `unsubscribe_execute`

当前：

- `get_email_headers`
- `parse_list_unsubscribe_header`
- `classify_unsubscribe_method`
- `post_one_click_unsubscribe`
- `parse_mailto_url`
- `send`
- `extract_unsubscribe_links_from_email`

改造后建议：

- `get_unsubscribe_info`
- `post_one_click_unsubscribe`
- `send`

新的 execute 流程：

1. 先调 `get_unsubscribe_info(email_ids=[email_id])`
2. 如果 `confirmed = false`
   - 直接返回确认提示，不执行
3. 如果 `method = one_click`
   - 取 `unsubscribe.options.one_click.request_payload`
   - 调 `post_one_click_unsubscribe(...)`
4. 如果 `method = mailto`
   - 取 `unsubscribe.options.mailto.send_payload`
   - 直接调 `send(...)`
5. 如果 `method = website`
   - 不自动打开网页
   - 直接使用新工具给出的 `manual_links`
   - 返回 `manual_required` 或 `manual_link_available`
6. 如果失败或不确定
   - 也优先使用新工具已经产出的 `manual_links`
   - 不再额外调正文提取工具

---

## 8. 旧工具的去留建议

### 8.1 建议保留

- `post_one_click_unsubscribe`

`post_one_click_unsubscribe` 职责清楚，保留是合理的。

### 8.2 建议逐步退出 skill 直接调用

- `get_email_headers`
- `parse_list_unsubscribe_header`
- `classify_unsubscribe_method`
- `parse_mailto_url`
- `extract_unsubscribe_links_from_email`

理由：

- 从 workflow 视角太底层
- skill 层不应该手工拼这几段状态
- 组合调用只会让 prompt 和调试都更复杂
- `extract_unsubscribe_links_from_email` 只服务 website/manual 场景，也应该由统一分析工具内部吸收

### 8.3 helper 可以继续存在

即使后续不再公开注册，下面这些函数依然可以作为内部 helper 保留：

- `_normalize_header_names`
- `_header_lookup`
- `parse_list_unsubscribe_header`
- `classify_unsubscribe_method`
- `parse_mailto_url`
- `_extract_unsubscribe_links_from_content`
- `extract_unsubscribe_links_from_email_tool`

也就是：

- “不公开暴露为工具”
- 不等于“底层实现必须删掉”

---

## 9. 文件改动范围

预计主要会改这些文件：

- `/Users/dingwenyu/Desktop/9900-H16C-Cake/email-agent/tools/unsubscribe_tools.py`
  - 新增 `get_unsubscribe_info`
  - 复用现有 helper
  - 把 website/manual link 提取逻辑内聚进新工具

- `/Users/dingwenyu/Desktop/9900-H16C-Cake/email-agent/agent.py`
  - 注册新工具
  - 视阶段决定是否移除旧工具注册

- `/Users/dingwenyu/Desktop/9900-H16C-Cake/email-agent/skills/registry.yaml`
  - 修改 `unsubscribe_discovery.used_tools`
  - 修改 `unsubscribe_execute.used_tools`

- `/Users/dingwenyu/Desktop/9900-H16C-Cake/email-agent/skills/unsubscribe_discovery.py`
  - 改成只依赖 `get_unsubscribe_info`

- `/Users/dingwenyu/Desktop/9900-H16C-Cake/email-agent/skills/unsubscribe_execute.py`
  - 改成读取统一 JSON
  - 不再手动串 header / parse / classify / manual-link fallback

- `/Users/dingwenyu/Desktop/9900-H16C-Cake/email-agent/tests/`
  - 补新工具和 skill 的测试

---

## 10. 测试计划

### 10.1 工具级测试

至少覆盖下面几类：

- 批量输入多个 `email_id`
- 只有 `one_click`
- 只有 `mailto`
- 同时有 `one_click + mailto`
- 只有 `website`
- header 中 `website` 存在
- header 不够，但正文中可提取 `manual_links`
- 没有 `List-Unsubscribe`
- `mailto` 缺少接收人
- Gmail API metadata 拉取失败

### 10.2 Skill 级测试

#### `unsubscribe_discovery`

- 候选邮件被正确分类
- 返回的代表邮件 id 和 method 正确
- 批量输入路径正确
- 不再依赖中间多段工具输出

#### `unsubscribe_execute`

- `confirmed = false` 时不执行
- `one_click` 时正确走 POST
- `mailto` 时正确走 `send`
- `website` 时返回 `manual_required` 或 `manual_link_available`
- 主执行失败时，优先使用统一分析结果里的 `manual_links`

---

## 11. 迁移建议

推荐按下面顺序做：

1. 新增 `get_unsubscribe_info`
2. 把 `website/manual link` 提取能力折进去
3. 先改两个 skill 去使用新工具
4. 保留旧工具注册一段时间，避免别处还在依赖
5. 等 skill 和日志都稳定后，再移除旧工具公开注册

这样风险最小。

---

## 12. 最终目标结构

最终希望 unsubscribe 相关链路收敛为：

### 读路径

- `search_emails`
- `get_unsubscribe_info`

### 执行路径

- `post_one_click_unsubscribe`
- `send`

这会比现在更清楚：

- 一个读工具负责“看清楚怎么退订”，同时整理 website/manual links
- 两个执行工具分别负责“POST 退订”和“发邮件退订”

---

## 13. 本文档结论

本次重构的核心不是“少几个函数”，而是把 unsubscribe 能力从“底层解析步骤”提升成“执行准备结果”。

推荐方向是：

1. 新增 `get_unsubscribe_info(email_ids)`
2. 让它支持批量分析多个邮件
3. 让它直接输出统一 JSON
4. 这个 JSON 同时包含：
   - 分类结果
   - `one_click` 执行参数
   - `mailto` 发送参数
   - `website` 手动链接
5. 让两个 unsubscribe skill 都改成围绕这个 JSON 工作

这样整个 unsubscribe 体系会更稳定，也更适合 skill workflow。
