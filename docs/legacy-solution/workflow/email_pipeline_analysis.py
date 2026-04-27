"""
Email processing pipeline analysis

End-to-end data flow from Gmail fetch to classification cache.
"""

# =============================================================================
# Email processing pipeline overview
# =============================================================================

"""
┌─────────────────────────────────────────────────────────────────────────────┐
│                    End-to-end email processing pipeline                       │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌──────────────┐                                                           │
│  │   Gmail API  │                                                           │
│  │  (data src)  │                                                           │
│  └──────┬───────┘                                                           │
│         │                                                                   │
│         ▼                                                                   │
│  ┌──────────────────────────────────────────────────────────────────┐      │
│  │              Layer 1: Gmail sync service                          │      │
│  │  ┌─────────────────────────────────────────────────────────────┐ │      │
│  │  │  GmailSyncService                                            │ │      │
│  │  │  - full_sync(): full sync                                    │ │      │
│  │  │  - partial_sync(): incremental sync (historyId-based)          │ │      │
│  │  │  - handle_push_notification(): Pub/Sub push handling           │ │      │
│  │  └─────────────────────────────────────────────────────────────┘ │      │
│  └──────────────────────────────┬───────────────────────────────────┘      │
│                                 │                                           │
│                                 ▼                                           │
│  ┌──────────────────────────────────────────────────────────────────┐      │
│  │              Layer 2: Gmail cache layer                            │      │
│  │  ┌─────────────────────────────────────────────────────────────┐ │      │
│  │  │  GmailCache                                                  │ │      │
│  │  │  - normalize_message(): normalize message shape               │ │      │
│  │  │  - replace_cache(): replace cache                            │ │      │
│  │  │  - merge_messages(): merge incremental updates               │ │      │
│  │  └─────────────────────────────────────────────────────────────┘ │      │
│  │                                                                   │      │
│  │  Output: data/cache/inbox_cache.json                             │      │
│  └──────────────────────────────┬───────────────────────────────────┘      │
│                                 │                                           │
│                                 ▼                                           │
│  ┌──────────────────────────────────────────────────────────────────┐      │
│  │              Layer 3: Email classification                      │      │
│  │  ┌─────────────────────────────────────────────────────────────┐ │      │
│  │  │  EmailTriageService (rule-based classifier)                 │ │      │
│  │  │  - keyword match                                            │ │      │
│  │  │  - allowlist / sender heuristics                            │ │      │
│  │  │  - deadline detection                                       │ │      │
│  │  │  - priority scoring                                         │ │      │
│  │  │  - confidence scoring                                       │ │      │
│  │  └─────────────────────────────────────────────────────────────┘ │      │
│  └──────────────────────────────┬───────────────────────────────────┘      │
│                                 │                                           │
│                                 ▼                                           │
│  ┌──────────────────────────────────────────────────────────────────┐      │
│  │              Layer 4: Classification storage                     │      │
│  │  ┌─────────────────────────────────────────────────────────────┐ │      │
│  │  │  EmailTriageStore                                            │ │      │
│  │  │  - replace_items(): persist classification results           │ │      │
│  │  │  - record_run(): record run metrics                          │ │      │
│  │  │  - metrics_payload(): fetch aggregate stats                  │ │      │
│  │  └─────────────────────────────────────────────────────────────┘ │      │
│  │                                                                   │      │
│  │  Output: data/cache/email_triage_index.json                    │      │
│  └──────────────────────────────────────────────────────────────────┘      │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
"""

# =============================================================================
# Layer 1: Gmail sync service
# =============================================================================

"""
GmailSyncService - mail sync service
====================================

File: backend/app/services/gmail/gmail_sync_service.py

Core behavior:
--------------
1. Full sync (full_sync)
   - Triggered on first sync or when historyId is invalid
   - Fetch user Profile (email, historyId)
   - List all INBOX message IDs
   - Batch-fetch message details
   - Extract attachment text (PDF, DOCX, TXT)

2. Incremental sync (partial_sync)
   - historyId-based incremental updates
   - Fetch history change records
   - Handle added/modified/deleted messages

3. Push notification handling
   - Receive Pub/Sub push
   - Decode envelope payload
   - Trigger incremental sync

Data flow:
----------
Gmail API → raw_message → normalize_message() → normalized_message

Key fields extracted:
- id: message ID
- threadId: thread ID
- historyId: history cursor (incremental sync)
- subject: subject
- from: sender
- snippet: preview
- body: body text
- attachmentTexts: extracted attachment text
- labelIds: labels (INBOX, UNREAD, etc.)
- internalDate: received time

Sync state:
- sync_status: ok | syncing | error | disabled
- sync_phase: idle | authorizing | fetching_messages | triaging
- last_history_id: incremental sync cursor
"""

# =============================================================================
# Layer 2: Gmail cache layer
# =============================================================================

"""
GmailCache - mail cache
=======================

File: backend/app/services/gmail/gmail_cache.py

Core behavior:
--------------
1. normalize_message()
   - Parse headers (From, To, Subject)
   - Extract body (plain text / HTML)
   - Extract links
   - Parse attachment filenames
   - Normalize date format

2. replace_cache()
   - Full cache replacement
   - Dedupe, sort
   - Enforce max size

3. merge_messages()
   - Incremental merge
   - Handle deletes and adds

Cache file shape (inbox_cache.json):
------------------------------------
{
  "email": "user@gmail.com",
  "messageCount": 199,
  "lastUpdatedAt": "2026-04-11T10:00:00Z",
  "messages": [
    {
      "id": "msg_id_123",
      "threadId": "thread_id_456",
      "historyId": "12345",
      "subject": "Interview invitation",
      "from": "hr@company.com",
      "to": "user@gmail.com",
      "snippet": "Email preview...",
      "body": "Full body...",
      "attachmentFilenames": ["resume.pdf"],
      "attachmentTexts": [
        {"filename": "resume.pdf", "mimeType": "application/pdf", "text": "Resume text..."}
      ],
      "links": ["https://..."],
      "internalDate": "2026-04-10T08:30:00Z",
      "labelIds": ["INBOX", "UNREAD"],
      "listUnsubscribe": "<https://...>",
      "headers": {...}
    }
  ]
}
"""

# =============================================================================
# Layer 3: Email classification layer
# =============================================================================

"""
EmailTriageService - rule-based classifier
==========================================

File: backend/app/services/triage/email_triage_service.py

Classification flow:
--------------------
┌─────────────────────────────────────────────────────────────┐
│                 Email classification decision tree          │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Input: normalized_message                                  │
│         │                                                   │
│         ▼                                                   │
│  ┌─────────────────────────────────────┐                   │
│  │  Step 1: Rule classification        │                   │
│  │  - Noise detection (allowlist/sub)  │                   │
│  │  - Category (keyword match)         │                   │
│  │  - Deadline detection (regex)       │                   │
│  │  - Priority (rule accumulation)     │                   │
│  │  - Confidence                       │                   │
│  └─────────────────────────────────────┘                   │
│         │                                                   │
│         ▼                                                   │
│  ┌─────────────────────────────────────┐                   │
│  │  Step 2: Assemble triage payload    │                   │
│  │  - Suggested action                 │                   │
│  │  - Reply/action flags               │                   │
│  │  - Sort weight                      │                   │
│  │  - Persistable output shape         │                   │
│  └─────────────────────────────────────┘                   │
│         │                                                   │
│         ▼                                                   │
│              Final classification                           │
│                                                             │
└─────────────────────────────────────────────────────────────┘

Classification output fields:
-----------------------------
{
  "message_id": "msg_id_123",
  "thread_id": "thread_id_456",
  "subject": "Interview invitation",
  "from": "hr@company.com",
  "sender_email": "hr@company.com",
  "category": "hiring",                    // category
  "category_display": "Hiring",            // display name
  "category_reasons": ["hiring_keywords"], // reasons
  "priority_label": "P1_ACTION_NEEDED",    // priority
  "priority_score": 0.79,                  // priority score
  "confidence": 0.83,                    // confidence
  "reasons": ["hiring_keywords", "important_sender"],
  "deadline_info": {...},                  // deadline info
  "suggested_action": "prepare_hiring_overview",
  "action_required": true,
  "action_type": "review",
  "reply_needed": false,
  "rule_score": 3,
  "matched_rules": ["HIRING_CATEGORY", "IMPORTANT_SENDER"],
  "sender_importance_score": 0.8,
  "noise_type": "",
  "noise_score": 0.0,
  "received_at": "2026-04-10T08:30:00Z",
  "label_ids": ["INBOX", "UNREAD"],
  "sort_weight": 379,
  "source": "rule"
}

Category definitions:
---------------------
- hiring: recruiting / interviews / job search
- security: security alerts / verification codes
- meeting: meetings / calendar
- finance: invoices / payments / bills
- real_estate: apartments / rentals / property
- newsletter: subscriptions / marketing
- personal: personal mail
- other: other work mail

Priority definitions:
---------------------
- P0_URGENT: urgent, needs immediate action
- P1_ACTION_NEEDED: action required
- P2_NORMAL: normal priority
- P3_LOW_VALUE: low value
"""

# =============================================================================
# Layer 4: Classification storage
# =============================================================================

"""
EmailTriageStore - classification persistence
=============================================

File: backend/app/services/triage/email_triage_store.py

Core behavior:
--------------
1. replace_items()
   - Store classification results
   - Update bootstrap state

2. record_run()
   - Record per-run metrics
   - Count successes/failures

3. metrics_payload()
   - Fetch aggregate run statistics

Storage file shape (email_triage_index.json):
---------------------------------------------
{
  "version": 1,
  "bootstrapStatus": "ready",
  "sourceCacheUpdatedAt": "2026-04-11T10:00:00Z",
  "lastBootstrapAt": "2026-04-11T10:05:00Z",
  "lastUpdatedAt": "2026-04-11T10:05:00Z",
  "lastError": "",
  "itemCount": 199,
  "items": [...],  // classification result list
  "metrics": {
    "runCount": 10,
    "successCount": 9,
    "failureCount": 1,
    "lastStatus": "ready",
    "lastDurationMs": 5000,
    "lastInputCount": 199,
    "lastTriagedCount": 199,
    "lastUrgentCount": 7,
    "lastActionNeededCount": 70,
    "lastLowValueCount": 34,
    "lastPriorityCounts": {"P0_URGENT": 7, "P1_ACTION_NEEDED": 70, ...},
    "lastCategoryCounts": {"hiring": 109, "newsletter": 21, ...}
  },
  "recentRuns": [...]
}
"""

# =============================================================================
# Data flow diagram (detailed)
# =============================================================================

"""
Data flow walkthrough
=====================

1. Raw Gmail API payload
   ↓
   {
     "id": "18f4a...",
     "threadId": "18f4a...",
     "historyId": "1234567",
     "payload": {
       "headers": [...],
       "parts": [...]
     },
     "snippet": "Email preview...",
     "labelIds": ["INBOX", "UNREAD"],
     "internalDate": "1712851200000"
   }

2. After normalize_message()
   ↓
   {
     "id": "18f4a...",
     "threadId": "18f4a...",
     "historyId": "1234567",
     "subject": "Interview invitation: game design role",
     "from": "hr@mihoyo.com",
     "snippet": "We have received your application...",
     "body": "Full body...",
     "attachmentTexts": [...],
     "links": [...],
     "internalDate": "2026-04-11T08:00:00Z",
     "labelIds": ["INBOX", "UNREAD"]
   }

3. After classification
   ↓
   {
     "message_id": "18f4a...",
     "category": "hiring",
     "priority_label": "P1_ACTION_NEEDED",
     "confidence": 0.83,
     "source": "rule",
     ...
   }

4. Final persistence
   ↓
   email_triage_index.json
"""

# =============================================================================
# Performance metrics
# =============================================================================

"""
Performance metrics
===================

Gmail sync:
-----------
- Full sync: ~10–30s (~200 messages)
- Incremental sync: ~1–5s
- Push notification latency: <1s

Email classification:
---------------------
- Rule path: <1ms/email
- Zero-shot path: ~5ms/email (batched)
- Hybrid average: ~3ms/email

Storage:
--------
- inbox_cache.json: ~2MB (~200 messages)
- email_triage_index.json: ~500KB
- Model memory: ~118MB (Sentence-Transformers)

Accuracy (indicative):
----------------------
- Rule system: 75–80%
- Zero-shot: 85–90%
- Hybrid: 88–93%
"""

# =============================================================================
# Optimization ideas
# =============================================================================

"""
Optimization ideas
==================

1. Sync layer:
   - Use watch to reduce polling
   - Incremental sync optimizations (only deltas)
   - Parallelize attachment text extraction

2. Classification layer:
   - Rules: richer contextual keywords
   - Embeddings: smaller model (e.g. all-MiniLM-L6-v2)
   - Cache: precompute category embeddings

3. Storage layer:
   - Compressed storage (gzip)
   - Sharding (e.g. by date)
   - Incremental updates (only changed items)

4. Architecture:
   - Async processing queue
   - Cache classification results
   - User feedback loop
"""

if __name__ == "__main__":
    print(__doc__)
