# Email Agent 工具清单

这份文档整理的是当前 `email-agent` 在你这套运行配置下实际暴露出来的工具。

- 当前模式：Gmail + Google Calendar + Memory + Shell + Todo + CRM 子流程
- 当前模型：`gpt-5.4`
- 当前工具数量：`50`
- 说明依据：运行中的 `email-agent` 工具注册表，而不是手工猜测

如果后面把 `.env` 切到 Outlook 模式，这份清单会变化。

## 1. Gmail / 邮件工具

### `add_label`
- 中文说明：给指定邮件添加标签。
- 主要作用：整理邮件分类。
- 常用参数：`email_id`, `label`

### `analyze_contact`
- 中文说明：用 LLM 深度分析某个联系人。
- 主要作用：补充联系人关系、语境、重要性等 CRM 信息。
- 常用参数：`email`, `max_emails`

### `archive_email`
- 中文说明：归档邮件，把邮件从 inbox 移走。
- 主要作用：清理收件箱。
- 常用参数：`email_id`

### `bulk_update_contacts`
- 中文说明：批量更新联系人。
- 主要作用：高效批量写入 CRM 字段，适合初始化联系人数据库时使用。
- 常用参数：`updates`

### `count_unread`
- 中文说明：统计未读邮件数量。
- 主要作用：快速了解未处理邮件规模。

### `detect_all_my_emails`
- 中文说明：检测这个账号实际接收邮件的所有邮箱地址和别名。
- 主要作用：识别转发地址、别名地址、路由地址。
- 常用参数：`max_emails`

### `get_all_contacts`
- 中文说明：从邮件中提取全部唯一联系人和联系频次。
- 主要作用：生成联系人全集。
- 注意：会覆盖 `contacts.csv`。
- 常用参数：`max_emails`, `exclude_automated`, `exclude_domains`

### `get_all_emails`
- 中文说明：读取所有文件夹中的邮件。
- 主要作用：不局限于 inbox，做全局邮件浏览。
- 常用参数：`max_results`

### `get_all_my_emails`
- 中文说明：返回和当前账号关联的全部邮箱地址。
- 主要作用：识别“我自己”的所有地址，避免联系人分析误判。
- 常用参数：`max_emails`

### `get_cached_contacts`
- 中文说明：从本地 CSV 缓存里读取联系人。
- 主要作用：快速拿联系人，不触发邮箱 API。

### `get_email_attachments`
- 中文说明：列出某封邮件的附件。
- 主要作用：确认邮件有没有附件、附件叫什么。
- 常用参数：`email_id`

### `get_email_body`
- 中文说明：读取邮件完整正文。
- 主要作用：在摘要不够时查看原文内容。
- 常用参数：`email_id`

### `get_emails_with_label`
- 中文说明：读取带某个标签的邮件。
- 主要作用：按 Gmail 标签筛邮件。
- 常用参数：`label`, `max_results`

### `get_labels`
- 中文说明：列出 Gmail 中的所有标签。
- 主要作用：让 agent 知道现有分类体系。

### `get_my_identity`
- 中文说明：获取当前用户的主邮箱和别名。
- 主要作用：明确“我是谁”，避免回信或联系人分析时混淆。

### `get_sent_emails`
- 中文说明：获取你已经发出的邮件。
- 主要作用：查看自己的发信历史和语气风格。
- 常用参数：`max_results`

### `get_unanswered_emails`
- 中文说明：找出最近一段时间内你还没回复的邮件。
- 主要作用：挖出需要 follow-up 的邮件。
- 常用参数：`within_days`, `max_results`

### `mark_read`
- 中文说明：把邮件标记为已读。
- 主要作用：处理已看过邮件。
- 常用参数：`email_id`

### `mark_unread`
- 中文说明：把邮件标记为未读。
- 主要作用：把需要稍后处理的邮件重新挂起来。
- 常用参数：`email_id`

### `read_inbox`
- 中文说明：读取 inbox 邮件列表。
- 主要作用：看最近邮件，或只看未读邮件。
- 常用参数：`last`, `unread`

### `reply`
- 中文说明：回复某封邮件。
- 主要作用：在原邮件线程里发送回复。
- 常用参数：`email_id`, `body`

### `search_emails`
- 中文说明：用 Gmail 搜索语法搜索邮件。
- 主要作用：按发件人、主题、日期、关键词等检索邮件。
- 常用参数：`query`, `max_results`

### `send`
- 中文说明：发送新邮件。
- 主要作用：主动发出一封新邮件。
- 常用参数：`to`, `subject`, `body`, `cc`, `bcc`

### `star_email`
- 中文说明：给邮件加星标。
- 主要作用：标记重要邮件。
- 常用参数：`email_id`

### `sync_contacts`
- 中文说明：同步联系人。
- 主要作用：增量更新联系人缓存，同时尽量保留已有 CRM 字段。
- 常用参数：`max_emails`, `exclude_domains`

### `sync_emails`
- 中文说明：把邮件同步到本地 CSV 缓存。
- 主要作用：增量缓存邮件全文，用于后续分析。
- 常用参数：`days_back`

### `update_contact`
- 中文说明：更新单个联系人的 CRM 字段。
- 主要作用：写联系人类型、关系、优先级、标签、跟进日期、备注等。
- 常用参数：`email`, `type`, `company`, `relationship`, `priority`, `deal`, `next_contact_date`, `tags`, `notes`, `last_contact`

## 2. Calendar / 日历工具

### `create_event`
- 中文说明：创建一个新的日历事件。
- 主要作用：建普通 calendar event。
- 常用参数：`title`, `start_time`, `end_time`, `description`, `attendees`, `location`

### `create_meet`
- 中文说明：创建一个 Google Meet 会议。
- 主要作用：建带 Meet 链接的会议邀请。
- 常用参数：`title`, `start_time`, `end_time`, `attendees`, `description`

### `delete_event`
- 中文说明：删除一个日历事件。
- 主要作用：取消已存在的会议或事件。
- 常用参数：`event_id`

### `find_free_slots`
- 中文说明：查某一天的空闲时间段。
- 主要作用：排会前先找可用时间。
- 常用参数：`date`, `duration_minutes`

### `get_event`
- 中文说明：获取某个事件的详细信息。
- 主要作用：查看单个事件的完整内容。
- 常用参数：`event_id`

### `get_today_events`
- 中文说明：获取今天的日历事件。
- 主要作用：快速看今日日程。

### `get_upcoming_meetings`
- 中文说明：获取未来一段时间内的会议。
- 主要作用：看近期带参会人的会议安排。
- 常用参数：`days_ahead`

### `list_events`
- 中文说明：列出未来一段时间内的日历事件。
- 主要作用：查看 upcoming events 总览。
- 常用参数：`days_ahead`, `max_results`

### `update_event`
- 中文说明：更新已有日历事件。
- 主要作用：改时间、标题、参会人、地点、描述等。
- 常用参数：`event_id`, `title`, `start_time`, `end_time`, `description`, `attendees`, `location`

## 3. Memory / 长期记忆工具

### `list_memories`
- 中文说明：列出所有 memory key。
- 主要作用：看当前有哪些长期记忆可读。

### `read_memory`
- 中文说明：读取某条 memory。
- 主要作用：拿联系人资料、CRM 汇总、用户偏好等。
- 常用参数：`key`

### `search_memory`
- 中文说明：按正则模式搜索 memory。
- 主要作用：模糊查找历史记忆条目。
- 常用参数：`pattern`

### `write_memory`
- 中文说明：写入 memory。
- 主要作用：把联系人分析、CRM 报告、用户偏好等持久化。
- 常用参数：`key`, `content`

## 4. Shell / 命令行工具

### `run`
- 中文说明：执行一条 shell 命令。
- 主要作用：取当前日期、做简单计算、查询系统信息。
- 常用参数：`command`, `timeout`

### `run_in_dir`
- 中文说明：在指定目录下执行 shell 命令。
- 主要作用：需要切目录时再执行命令。
- 常用参数：`command`, `directory`, `timeout`

## 5. Todo / 任务列表工具

### `add`
- 中文说明：新增一条 todo。
- 主要作用：把复杂任务拆成待办事项。
- 常用参数：`content`, `active_form`

### `clear`
- 中文说明：清空所有 todo。
- 主要作用：重置任务列表。

### `complete`
- 中文说明：把某条 todo 标记为已完成。
- 主要作用：推进任务状态。
- 常用参数：`content`

### `list`
- 中文说明：列出当前所有 todo。
- 主要作用：查看任务清单。

### `remove`
- 中文说明：删除某条 todo。
- 主要作用：移除无效或不需要的任务。
- 常用参数：`content`

### `start`
- 中文说明：把某条 todo 标记为进行中。
- 主要作用：表示任务正在处理。
- 常用参数：`content`

### `update`
- 中文说明：整批替换整个 todo 列表。
- 主要作用：做批量重排或整体刷新。
- 常用参数：`todos`

## 6. CRM 子流程工具

### `init_crm_database`
- 中文说明：初始化 CRM 数据库。
- 主要作用：这是主 agent 暴露出来的一个包装工具，内部会调用子 agent `crm-init` 去完成联系人提取、分类、未回复邮件发现和 memory 写入。
- 常用参数：`max_emails`, `top_n`, `exclude_domains`

## 7. 补充说明

### 这些工具是怎么给模型看的
- 模型看到的不是工具源码，而是工具名、简短描述、参数 schema。
- 这些 schema 主要来自 Python 函数签名和类型注解。

### 为什么有些操作会要求确认
- 发邮件和改日历这类写操作，不只是 prompt 决定，还会被插件拦截。
- 当前 Gmail 模式下，`send` / `reply` 会被 `gmail_plugin` 审批。
- 当前 Calendar 写操作会被 `calendar_plugin` 审批。

### 为什么有些工具看起来像“内部能力”
- `init_crm_database` 这种工具不是直接对应 Gmail API，而是本地 Python 函数。
- 它的作用是把一个复杂多步流程包装成一个可供主模型调用的单一工具。
