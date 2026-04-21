# Skill: `resume_candidate_review`

## 目标

识别"简历 / 求职 / 候选人 / 职位申请"类邮件，并在附件可用时提取其中的文本，组合出一份供招聘方快速审阅的 bundle。

代码：`email-agent/skills/resume_candidate_review.py`。

---

## 关键词

```python
RESUME_QUERY_TERMS = (
    "candidate", "applicant", "application", "resume", "cv", "portfolio",
    '"job application"', '"application for"', '"applying for"',
    '"cover letter"', '"candidate profile"', '"candidate submission"',
    '"resume attached"', '"cv attached"',
)
```

Gmail 查询：`in:inbox newer_than:{days}d ({terms})`。
`MAX_LOOKBACK_DAYS = 7`、`SEARCH_MAX_RESULTS = 350`。

---

## 三阶段流程

1. **search_emails** —— 用上面的查询拉出候选邮件。
2. **get_email_attachments** —— 对每封候选邮件调用一次；通过 `_attachment_list_has_files` 判定是否带附件。
3. **extract_recent_attachment_texts** —— 当至少一封命中邮件有附件时，用 `{search_query} has:attachment` 运行一次附件文本抽取，再按 `Message ID` 过滤出与候选邮件对应的段落。

这样设计的原因：附件抽取工具比较昂贵，按命中 id 过滤避免把无关附件丢给 Finalizer。

---

## Bundle 关键段

```
[RESUME_CANDIDATE_REVIEW_BUNDLE]
skill_name: resume_candidate_review
days: 7
search_query: ...
resume_keywords: ...
matched_candidate_email_count: N
attachment_checks_count: N
matched_candidate_emails_with_attachments: M
attachment_extraction_called: true|false
notes:
- Finalizer instruction: 以附件文本为首要依据，没有就用搜索命中 / 附件清单。
- Finalizer instruction: 如果命中不是真实候选人材料，忽略。
- 不要编造年限 / 技能 / role fit。

[SEARCH_EMAILS] ...
[MATCHED_CANDIDATE_EMAIL_IDS] ...
[ATTACHMENT_CHECK_RESULTS] ...
[EMAIL_ATTACHMENTS_1..N] ...
[MATCHED_CANDIDATE_EMAIL_IDS_WITH_ATTACHMENTS] ...
[ATTACHMENT_EXTRACTION_CALL] ...
[RELEVANT_ATTACHMENT_TEXT_EXTRACTIONS] ...
```

---

## Finalizer 期望

每个候选人输出：

- **Identity**（若可识别）
- **目标岗位 / 意向**
- **附件证据**（有无简历 / CL）
- **关键背景 / 技能**（只能来自附件文本）
- **不足 / 缺失证据**
- **下一步建议**（约面试 / 索要更多材料 / 不匹配）

当附件抽取失败或为空：要显式说明"附件文本缺失，以下内容为有限信息"，不得编写候选人资历。
