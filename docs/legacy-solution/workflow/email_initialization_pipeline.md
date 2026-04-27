# Email Initialization Pipeline

## 📊 Pipeline Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         EMAIL INITIALIZATION PIPELINE                        │
└─────────────────────────────────────────────────────────────────────────────┘

┌──────────────┐    ┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│   Frontend   │───▶│   Backend    │───▶│  Gmail Sync  │───▶│  Triage      │
│  Dashboard   │    │   Startup    │    │   Service    │    │  Service     │
└──────────────┘    └──────────────┘    └──────────────┘    └──────────────┘
                                                                   │
                                                                   ▼
                          ┌────────────────────────────────────────────────┐
                          │              DERIVED DATA                      │
                          │  ┌─────────────┐  ┌─────────────┐  ┌─────────┐ │
                          │  │ Morning     │  │ Writing     │  │ Priority│ │
                          │  │ Brief       │  │ Style       │  │ Inbox   │ │
                          │  └─────────────┘  └─────────────┘  └─────────┘ │
                          └────────────────────────────────────────────────┘
```

---

## 🔄 Stage 1: Backend Startup

**File:** `backend/app/main.py`

```python
# Lifespan hook starts background services
@asynccontextmanager
async def app_lifespan(_: FastAPI):
    _start_background_services()  # ← Entry point
    try:
        yield
    finally:
        _stop_background_services()
```

**Actions:**
1. Initialize `EmailAgentClient`
2. Get `DashboardStatusService`
3. Call `start_background_sync()`

**Console Output:**
```
[Dashboard] Contact list is still empty...
[Dashboard] Memory profile has not been curated yet.
[Dashboard] Core memory files are initialized (9/9).
```

---

## 🔄 Stage 2: Background Sync Start

**File:** `backend/app/services/common/dashboard_status.py`

```python
def start_background_sync(self) -> None:
    self._gmail_sync_service.start_background_loop()  # 1. Start sync loop
    self._gmail_sync_service.ensure_cache_pipeline()  # 2. Ensure derived data
    self._scheduled_task_service.sync_from_preferences()
    self._scheduled_task_service.tick()
    self._scheduled_task_service.start_background_loop()
```

**Console Output:**
```
[Dashboard] Automatic Gmail sync started.
```

---

## 🔄 Stage 3: Gmail Sync (Full Sync)

**File:** `backend/app/services/gmail/gmail_sync_service.py`

### Phase 3.1: Fetch Messages

```
┌─────────────────────────────────────────────────────────────────┐
│                    GMAIL FULL SYNC FLOW                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  1. Authenticate with Gmail API                                 │
│     └── GmailCredentialsService.get_credentials()               │
│                                                                 │
│  2. Fetch message list (max 500 messages)                       │
│     └── users.messages.list() → message IDs                     │
│                                                                 │
│  3. Fetch message content (batch of 25)                         │
│     └── users.messages.get() → full message data                │
│     └── Progress: 100/500, 200/500, 300/500...                  │
│                                                                 │
│  4. Extract attachments (if relevant)                           │
│     └── PDF, DOCX, TXT, HTML extraction                         │
│                                                                 │
│  5. Write to cache                                              │
│     └── GmailCache.write_cache() → inbox_cache.json             │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

**Console Output:**
```
[Dashboard] Syncing emails: fetching Gmail message content (100/500).
[Dashboard] Syncing emails: fetching Gmail message content (200/500).
[Dashboard] Syncing emails: fetching Gmail message content (300/500).
[Dashboard] Syncing emails: fetching Gmail message content (400/500).
[Dashboard] Inbox cache updated. 500 cached emails available.
```

### Phase 3.2: Cache Structure

**File:** `data/cache/inbox_cache.json`

```json
{
  "lastUpdatedAt": "2026-04-13T01:28:45.000Z",
  "messageCount": 500,
  "messages": [
    {
      "id": "msg_123",
      "threadId": "thread_abc",
      "from": "sender@example.com",
      "to": "user@example.com",
      "subject": "Email Subject",
      "snippet": "Email preview text...",
      "internalDate": "2026-04-12T10:00:00Z",
      "labelIds": ["INBOX", "UNREAD"],
      "attachments": [...]
    }
  ]
}
```

---

## 🔄 Stage 4: Email Triage/Analysis

**File:** `backend/app/services/triage/email_triage_service.py`

```
┌─────────────────────────────────────────────────────────────────┐
│                    EMAIL TRIAGE PIPELINE                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Input: 500 cached messages                                     │
│                                                                 │
│  For each message:                                              │
│    1. Classify category                                         │
│       ├── hiring, meeting, finance, security                    │
│       ├── real_estate, newsletter, notification, personal       │
│       └── other                                                 │
│                                                                 │
│    2. Calculate priority                                        │
│       ├── P0_URGENT      → immediate action                     │
│       ├── P1_ACTION_NEEDED → reply/confirm/review               │
│       ├── P2_NORMAL      → regular handling                     │
│       └── P3_LOW_VALUE   → archive/unsubscribe                  │
│                                                                 │
│    3. Detect deadlines                                          │
│       ├── English: "by 5pm", "tomorrow", "within 3 days"        │
│       └── Chinese text: within-N-day windows, tonight, deadlines │
│                                                                 │
│    4. Determine action                                          │
│       ├── reply_needed: true/false                              │
│       ├── suggested_action: "review_and_reply", "archive"...    │
│       └── deadline_info: {...}                                  │
│                                                                 │
│  Output: Triage index with 500 classified items                 │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

**Console Output:**
```
[Dashboard] Analyzing synced emails.
[Dashboard] Inbox analysis completed. Funnel classified 500 cached emails: 2 urgent, 47 actionable, 361 low-value.
```

### Triage Output Structure

**File:** `data/cache/email_triage_index.json`

```json
{
  "bootstrapStatus": "ready",
  "sourceCacheUpdatedAt": "2026-04-13T01:28:45.000Z",
  "lastBootstrapAt": "2026-04-13T01:29:00.000Z",
  "items": [
    {
      "message_id": "msg_123",
      "thread_id": "thread_abc",
      "subject": "Interview Confirmation",
      "from": "recruiter@techcorp.com",
      "category": "hiring",
      "priority_label": "P0_URGENT",
      "priority_score": 0.94,
      "confidence": 0.92,
      "action_required": true,
      "suggested_action": "prepare_hiring_overview",
      "reply_needed": true,
      "deadline_info": {
        "detected": true,
        "text": "tomorrow 2pm",
        "hours_left": 18.5
      }
    }
  ]
}
```

---

## 🔄 Stage 5: Derived Data Generation

### 5.1 Morning Brief

**File:** `backend/app/services/workflow/morning_brief_service.py`

```
┌─────────────────────────────────────────────────────────────────┐
│                    MORNING BRIEF GENERATION                     │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Input:                                                         │
│    - Cached messages (last 14 days)                             │
│    - Triage results                                             │
│    - Follow-up candidates                                       │
│                                                                 │
│  Process:                                                       │
│    1. Filter messages within window                             │
│    2. Aggregate by topic                                        │
│    3. Identify urgent items                                     │
│    4. Find follow-up candidates                                 │
│    5. Generate LLM summary (optional)                           │
│                                                                 │
│  Output: Morning brief JSON                                     │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

**Output Structure:**
```json
{
  "summaryDate": "2026-04-13",
  "generatedAt": "2026-04-13T01:29:00.000Z",
  "title": "2 urgent threads on Apr 13, 2026",
  "excerpt": "2 urgent threads need immediate attention...",
  "messageCount": 47,
  "urgentCount": 2,
  "needsReplyCount": 5,
  "topics": ["hiring", "meeting", "finance"],
  "markdown": "## Today at a Glance\n..."
}
```

### 5.2 Writing Style Profile

**File:** `data/profile/writing_style.md`

```
Status: Ready if file exists and has content
Source: User's sent emails analysis
Purpose: Signature/greeting/closing patterns for draft generation
```

### 5.3 Memory Profile

**File:** `data/memory/memory_profile.json`

```
Status: Curated after manual or automatic curation
Source: User interactions and preferences
Purpose: Long-term context for agent
```

---

## 📈 Complete Pipeline Timeline

```
Time    Stage                    Status                    Console Output
────────────────────────────────────────────────────────────────────────────
T+0s    Backend Startup          Starting                  [backend.startup.preload.begin]
T+0.1s  Dashboard Service        Initializing              [Dashboard] Core memory files initialized
T+0.2s  Gmail Sync               Starting                  [Dashboard] Automatic Gmail sync started
T+0.3s  Gmail Auth               Checking                  (credential validation)
T+1s    Message Fetch            100/500                   Syncing emails: fetching (100/500)
T+3s    Message Fetch            200/500                   Syncing emails: fetching (200/500)
T+5s    Message Fetch            300/500                   Syncing emails: fetching (300/500)
T+7s    Message Fetch            400/500                   Syncing emails: fetching (400/500)
T+9s    Cache Update             Complete                  Inbox cache updated. 500 cached emails
T+9.5s  Triage Start             Processing                Analyzing synced emails
T+12s   Triage Complete          Ready                     Inbox analysis completed. 2 urgent, 47 actionable
T+13s   Morning Brief            Generated                 (saved to memory store)
T+14s   Pipeline Complete        Ready                     [backend.startup.preload.ready]
```

---

## 🗂️ File Structure After Initialization

```
data/
├── cache/
│   ├── inbox_cache.json          # Gmail messages cache
│   ├── email_triage_index.json   # Triage results
│   └── gmail_sync_state.json     # Sync state
├── memory/
│   ├── memory_profile.json       # User memory profile
│   ├── session_snapshot.json     # Session context
│   ├── tasks.json                # Task list
│   ├── preferences.json          # User preferences
│   ├── projects.json             # Project context
│   ├── summary_index.json        # Summary index
│   ├── events.json               # Event history
│   ├── user_profile.json         # User profile
│   ├── unsubscribe_preferences.json
│   └── contacts.csv              # Contact database
├── profile/
│   └── writing_style.md          # Writing style profile
└── learned_patterns.json         # Learned patterns
```

---

## 🔧 Key Services & Responsibilities

| Service | File | Responsibility |
|---------|------|----------------|
| `GmailSyncService` | `gmail_sync_service.py` | Fetch & cache Gmail messages |
| `GmailCache` | `gmail_cache.py` | Read/write inbox cache |
| `EmailTriageService` | `email_triage_service.py` | Classify & prioritize emails |
| `MorningBriefService` | `morning_brief_service.py` | Generate daily briefings |
| `MemoryStore` | `memory_store.py` | Manage memory files |
| `ContactRepository` | `contact_repository.py` | Manage contacts |
| `FollowUpService` | `follow_up_service.py` | Track follow-up candidates |
| `DashboardStatusService` | `dashboard_status.py` | Aggregate all status |

---

## 🚦 Status Indicators

### Sync Status
| Value | Description |
|-------|-------------|
| `idle` | No active sync |
| `syncing` | Currently syncing |
| `ready` | Sync complete, cache fresh |
| `degraded` | Partial failure, using cache |
| `error` | Sync failed |
| `disabled` | Provider not configured |

### Cache Freshness
| Value | Description |
|-------|-------------|
| `fresh` | Synced within 2 minutes |
| `aging` | Synced 2-15 minutes ago |
| `stale` | Synced >15 minutes ago |
| `missing` | Never synced |
| `disabled` | Sync disabled |

### Triage Bootstrap Status
| Value | Description |
|-------|-------------|
| `not_started` | No triage run yet |
| `bootstrapping` | First triage in progress |
| `ready` | Triage complete |
| `degraded` | Triage partial failure |

---

## 📊 Current Progress (From Console)

```
✅ Backend: Operational
✅ Gmail Provider: Connected
✅ Gmail Auth: Ready
✅ Inbox Cache: 500 emails cached
✅ Triage: Complete (2 urgent, 47 actionable, 361 low-value)
✅ Morning Brief: Generated
⚠️  Contact List: Empty (background maintenance pending)
⚠️  Memory Profile: Not curated yet
✅ Core Memory Files: 9/9 initialized
✅ Writing Style: Ready (file exists)
```

---

## 🔍 Debug Trace Example

```json
{
  "debugTrace": [
    "backend=ok",
    "provider=configured",
    "auth_state=ready",
    "sync_status=ready",
    "sync_phase=idle",
    "sync_progress=none",
    "watch_status=active",
    "cache_freshness=fresh",
    "cached_message_count=500",
    "cache_updated_at=2026-04-13T01:28:45Z",
    "unread_count=12",
    "priority_count=2",
    "morning_brief_date=2026-04-13",
    "contacts_count=0",
    "writing_style=ready",
    "memory_profile=missing",
    "memory_bootstrap=9/9",
    "learned_pattern_count=0",
    "brief_cache_entries=0",
    "triage_status=ready",
    "triage_counts=500/500"
  ]
}
```

---

## 📝 API Endpoints for Pipeline Status

| Endpoint | Purpose |
|----------|---------|
| `GET /dashboard/status` | Full pipeline status |
| `POST /dashboard/status/sync` | Force sync |
| `GET /email-triage` | List triaged emails |
| `GET /email-triage/metrics` | Triage metrics |
| `GET /morning-briefs` | List morning briefs |
| `GET /memory-profile` | Get memory profile |
