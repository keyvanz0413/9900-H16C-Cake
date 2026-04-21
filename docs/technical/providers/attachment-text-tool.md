# Attachment Text Tool

## 目标

`extract_recent_attachment_texts(query, max_results=10)` 从 Gmail 最近邮件的附件中抽出纯文本，给 `resume_candidate_review` 这类需要读简历/CV 的技能使用。

代码：`email-agent/tools/attachment_text_tool.py`，仅在 Gmail 分支通过 `agent.py` 注入：

```python
def extract_recent_attachment_texts(query, max_results=10):
    email_tool = _get_primary_email_tool()
    if email_tool is None:
        return "Recent attachment text extraction is only available when Gmail is connected."
    return extract_recent_attachment_texts_from_email_tool(
        email_tool=email_tool, query=query, max_results=max_results,
    )
```

---

## 支持的格式

| 扩展名 | MIME | 处理 |
|---|---|---|
| `.txt` | `text/plain` | 直接 decode |
| `.md` | `text/markdown` | 直接 decode |
| `.html` | `text/html` | 去掉 `<script>/<style>`、常用块级 tag 转换行、剥 HTML |
| `.pdf` | `application/pdf` | `pypdf.PdfReader` 读取文本；加密 PDF 返回占位 |
| `.docx` | `application/vnd.openxmlformats-...` | 解 zip + 解析 `word/document.xml` |

不在白名单内的附件会被标记 `skipped (unsupported attachment type)`。

---

## 常量

```python
_ATTACHMENT_TEXT_LIMIT = 4000       # 每个附件最多保留 4000 字符
_SUPPORTED_EXTENSIONS = (".txt", ".md", ".html", ".pdf", ".docx")
```

截断策略：超过上限直接从尾部截，不做摘要。目的是避免把整个简历灌进 context。

---

## 错误处理

- `pypdf` 不存在 → 返回 `[PDF extraction unavailable: pypdf is not installed.]`。
- PDF 加密 → `[Encrypted PDF attachment: unable to extract text.]`。
- 空内容 → `skipped (empty attachment content)`。
- 其他异常（下载失败、zip 损坏）→ 按附件标记错误，整体函数不抛。

---

## 输出结构（文本段）

```
[ATTACHMENT_EXTRACTION]
query: ...
max_results: ...

[EMAIL_1]
Message ID: ...
From: ...
Subject: ...
Attachments:
- filename.pdf (application/pdf): <4000 字符文本>
- picture.png: skipped (unsupported attachment type)

[EMAIL_2]
...
```

`resume_candidate_review` 按 `Message ID` 过滤出与候选邮件匹配的段落（`_extract_relevant_attachment_text_sections`）。

---

## 只在 Gmail 分支注入

Outlook 分支当前没有等价工具。如果想移植，需要：

1. 用 Microsoft Graph API 的 `messages/{id}/attachments` 换 Gmail API。
2. 公共的解码/格式解析代码可以直接复用（`_strip_html`、`_decode_attachment_bytes` 等）。
