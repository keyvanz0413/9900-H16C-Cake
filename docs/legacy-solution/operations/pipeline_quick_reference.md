# Email Initialization Pipeline - Quick Reference

## 📊 Visual Pipeline Flow

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                          EMAIL INITIALIZATION PIPELINE                          │
└─────────────────────────────────────────────────────────────────────────────────┘

  START                                                                              END
    │                                                                                  │
    ▼                                                                                  ▼
┌─────────────┐   ┌─────────────┐   ┌─────────────┐   ┌─────────────┐   ┌─────────────┐
│   Backend   │──▶│  Gmail Sync │──▶│   Cache     │──▶│   Triage    │──▶│  Derived    │
│   Startup   │   │   Service   │   │   Update    │   │   Analysis  │   │    Data     │
└─────────────┘   └─────────────┘   └─────────────┘   └─────────────┘   └─────────────┘
      │                  │                  │                  │                  │
      ▼                  ▼                  ▼                  ▼                  ▼
   Init services     Fetch emails      Write cache        Classify          Morning Brief
   Memory files      100/500...        500 emails        P0-P3             Writing Style
   (9/9 ready)       Auth check        inbox_cache.json  triage_index      Memory Profile
                                                        2 urgent
                                                        47 actionable
```

---

## 📈 Current Status (Based on Console Output)

```
┌────────────────────────────────────────────────────────────────────┐
│                        CURRENT PIPELINE STATUS                      │
├────────────────────────────────────────────────────────────────────┤
│                                                                    │
│  ✅ Backend Startup           ──────────────────────── COMPLETE    │
│     └── Core memory files: 9/9 initialized                        │
│                                                                    │
│  ✅ Gmail Sync                ──────────────────────── COMPLETE    │
│     └── Status: ready, Phase: idle                                 │
│     └── Messages fetched: 500                                      │
│     └── Cache updated: 2026-04-13T01:28:45Z                       │
│                                                                    │
│  ✅ Inbox Cache               ──────────────────────── COMPLETE    │
│     └── 500 cached emails available                                │
│     └── Freshness: fresh                                           │
│                                                                    │
│  ✅ Email Triage              ──────────────────────── COMPLETE    │
│     └── Status: ready                                              │
│     └── Results: 2 urgent, 47 actionable, 361 low-value           │
│     └── 500/500 emails classified                                  │
│                                                                    │
│  ✅ Morning Brief             ──────────────────────── COMPLETE    │
│     └── Generated for: 2026-04-13                                  │
│                                                                    │
│  ⚠️  Contact List             ──────────────────────── PENDING     │
│     └── Background maintenance will populate                       │
│                                                                    │
│  ⚠️  Memory Profile           ──────────────────────── PENDING     │
│     └── Not curated yet                                            │
│                                                                    │
│  ✅ Writing Style             ──────────────────────── READY       │
│     └── File exists                                                │
│                                                                    │
└────────────────────────────────────────────────────────────────────┘
```

---

## 🔄 What Happens at Each Stage

### Stage 1: Backend Startup
```
Location: backend/app/main.py → _start_background_services()
Duration: ~0.2 seconds

Actions:
├── Initialize EmailAgentClient
├── Get DashboardStatusService
└── Call start_background_sync()

Console Output:
[Dashboard] Core memory files are initialized (9/9).
```

### Stage 2: Gmail Sync
```
Location: backend/app/services/gmail/gmail_sync_service.py
Duration: ~9 seconds (for 500 emails)

Actions:
├── Authenticate with Gmail API
├── Fetch message IDs (list)
├── Fetch message content (batch of 25)
├── Extract attachments (PDF, DOCX, TXT)
└── Write to inbox_cache.json

Console Output:
[Dashboard] Automatic Gmail sync started.
[Dashboard] Syncing emails: fetching Gmail message content (100/500).
[Dashboard] Syncing emails: fetching Gmail message content (200/500).
...
[Dashboard] Inbox cache updated. 500 cached emails available.
```

### Stage 3: Email Triage
```
Location: backend/app/services/triage/email_triage_service.py
Duration: ~3 seconds (for 500 emails)

Actions:
├── Read inbox_cache.json
├── For each message:
│   ├── Classify category (hiring, meeting, finance, etc.)
│   ├── Calculate priority (P0-P3)
│   ├── Detect deadlines
│   └── Determine suggested action
└── Write to email_triage_index.json

Console Output:
[Dashboard] Analyzing synced emails.
[Dashboard] Inbox analysis completed. Funnel classified 500 cached emails:
            2 urgent, 47 actionable, 361 low-value.
```

### Stage 4: Derived Data
```
Location: Multiple services
Duration: ~1 second

Actions:
├── Morning Brief Generation
│   └── morning_brief_service.py → memory_store
├── Writing Style (already exists)
│   └── data/profile/writing_style.md
└── Memory Profile (pending curation)
    └── memory_curator_service.py
```

---

## 📁 Key Data Files

| File | Purpose | Status |
|------|---------|--------|
| `data/cache/inbox_cache.json` | Gmail messages | ✅ Ready (500 emails) |
| `data/cache/email_triage_index.json` | Classification results | ✅ Ready |
| `data/cache/gmail_sync_state.json` | Sync state | ✅ Ready |
| `data/profile/writing_style.md` | Writing style profile | ✅ Ready |
| `data/memory/memory_profile.json` | User memory profile | ⚠️ Not curated |
| `data/memory/contacts.csv` | Contact database | ⚠️ Empty |

---

## 🎯 Next Steps (What's Pending)

1. **Contact List Population**
   - Background contact maintenance will populate when provider data is available
   - Source: Gmail sent emails analysis
   - Service: `contact_repository.py`

2. **Memory Profile Curation**
   - Requires manual or automatic curation
   - Service: `memory_curator_service.py`
   - Can be triggered via: `POST /memory-profile/curate`

---

## 🔍 Check Pipeline Status

### API Endpoint
```bash
curl http://localhost:8000/dashboard/status | jq '{
  sync_status: .syncStatus,
  sync_phase: .syncPhase,
  cache_freshness: .cacheFreshness,
  cached_count: .cachedMessageCount,
  triage_status: .triageBootstrapStatus,
  urgent_count: .triageLastUrgentCount,
  contacts_count: .contactsCount,
  writing_style: .writingStyleReady,
  memory_profile: .memoryProfileReady
}'
```

### Expected Response (Current State)
```json
{
  "sync_status": "ready",
  "sync_phase": "idle",
  "cache_freshness": "fresh",
  "cached_count": 500,
  "triage_status": "ready",
  "urgent_count": 2,
  "contacts_count": 0,
  "writing_style": true,
  "memory_profile": false
}
```
