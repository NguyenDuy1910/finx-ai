# FinX UI — Restructure Plan

## 🔍 Current Problems

| Problem | Where | Impact |
|---------|-------|--------|
| **God file** | `admin-container.tsx` (1,419 lines) with 10+ inline sub-components | Unmaintainable, hard to test |
| **God file** | `explore-container.tsx` (664 lines) with 4 inline sub-components | Same |
| **God file** | `playground-container.tsx` (394 lines) with inline sub-component | Same |
| **Mixed concerns** | `chat-container.tsx` mixes SSE parsing logic, scroll management, state, and rendering in one file | Hard to reuse/test |
| **Flat type barrel** | `types/index.ts` (245 lines) — all types in one file | No domain separation |
| **No hooks layer** | Business logic (API calls, scroll, clipboard) duplicated inside components | Not reusable |
| **No API service layer** | API calls scattered with `fetch()` directly inside components | Duplicated, hard to refactor |
| **No constants file** | Magic strings, config arrays (`AVAILABLE_DATABASES`, `NAV_ITEMS`) embedded in components | Scattered config |
| **No barrel exports** | Each component folder has no `index.ts` | Messy import paths |

## 🎯 New Structure

```
src/
├── app/                          # Next.js App Router (UNCHANGED — routes only)
│   ├── layout.tsx
│   ├── page.tsx
│   ├── globals.css
│   └── api/                      # API routes (keep as-is, they're clean)
│       ├── chat/route.ts
│       ├── health/route.ts
│       ├── search/...
│       ├── sessions/...
│       ├── tables/route.ts
│       ├── text2sql/route.ts
│       └── graph/...
│
├── components/
│   ├── ui/                       # Primitive UI components (keep as-is)
│   │   ├── badge.tsx
│   │   ├── button.tsx
│   │   ├── card.tsx
│   │   ├── collapsible.tsx
│   │   ├── input.tsx
│   │   ├── scroll-area.tsx
│   │   ├── select.tsx
│   │   ├── skeleton.tsx
│   │   ├── tabs.tsx
│   │   ├── textarea.tsx
│   │   └── index.ts              # NEW — barrel export
│   │
│   ├── shared/                   # NEW — reusable non-primitive components
│   │   ├── copy-button.tsx       # Extracted from chat-message, sql-block, admin
│   │   ├── error-banner.tsx      # Extracted repeated error UI pattern
│   │   ├── empty-state.tsx       # Extracted repeated empty state pattern
│   │   ├── loading-skeleton.tsx  # Extracted repeated skeleton pattern
│   │   ├── status-dot.tsx        # Extracted from header
│   │   └── index.ts
│   │
│   ├── layout/                   # App shell
│   │   ├── header.tsx
│   │   ├── sidebar.tsx
│   │   └── index.ts
│   │
│   ├── chat/                     # Chat feature
│   │   ├── chat-container.tsx    # SLIMMED — orchestrator only
│   │   ├── chat-input.tsx
│   │   ├── chat-message.tsx
│   │   ├── chat-welcome.tsx      # NEW — extracted welcome/empty state
│   │   ├── markdown-content.tsx
│   │   ├── sql-block.tsx
│   │   ├── thinking-block.tsx
│   │   ├── tool-call-block.tsx
│   │   └── index.ts
│   │
│   ├── explore/                  # Explore feature — SPLIT
│   │   ├── explore-container.tsx # Orchestrator only
│   │   ├── search-form.tsx       # Search + join path inputs
│   │   ├── search-results.tsx    # Results list
│   │   ├── search-result-card.tsx
│   │   ├── table-detail-panel.tsx
│   │   ├── join-path-panel.tsx
│   │   └── index.ts
│   │
│   ├── playground/               # Playground feature — SPLIT
│   │   ├── playground-container.tsx
│   │   ├── sql-result-card.tsx   # Extracted sub-component
│   │   └── index.ts
│   │
│   └── admin/                    # Admin feature — HEAVILY SPLIT
│       ├── admin-container.tsx   # Tabs shell only
│       ├── search-detail-panel.tsx
│       ├── search-result-renderer.tsx
│       ├── graph-stats-panel.tsx
│       ├── indexing-panel.tsx
│       ├── feedback-panel.tsx
│       └── index.ts
│
├── hooks/                        # NEW — custom hooks
│   ├── use-clipboard.ts          # Reusable copy-to-clipboard
│   ├── use-auto-scroll.ts        # Extracted from chat-container
│   ├── use-health-check.ts       # Extracted from header
│   └── index.ts
│
├── services/                     # NEW — API service layer
│   ├── api-client.ts             # fetchFromBackend + fetchJSON (moved from lib/api.ts)
│   ├── search.service.ts         # Client-side search API calls
│   ├── text2sql.service.ts       # Client-side text2sql calls
│   ├── graph.service.ts          # Client-side graph/admin calls
│   └── index.ts
│
├── lib/                          # Pure utility functions
│   ├── utils.ts                  # cn() helper (keep)
│   └── chat-store.ts             # Thread localStorage (keep)
│
├── types/                        # SPLIT by domain
│   ├── chat.types.ts
│   ├── search.types.ts
│   ├── admin.types.ts
│   ├── common.types.ts           # NavPage, ChatMode, shared enums
│   └── index.ts                  # Re-exports everything
│
└── constants/                    # NEW — app-wide constants
    ├── databases.ts              # AVAILABLE_DATABASES
    ├── navigation.ts             # NAV_ITEMS, NAV_LABELS
    ├── intents.ts                # INTENT_LABELS
    └── index.ts
```

## 📋 Execution Steps

### Phase 1: Create foundation (constants, types, hooks, services)
### Phase 2: Create shared components  
### Phase 3: Split god files (admin → 6 files, explore → 6 files, playground → 2 files)
### Phase 4: Slim down chat-container
### Phase 5: Update imports in page.tsx, header.tsx, sidebar.tsx
### Phase 6: Add barrel exports (index.ts) to every folder
### Phase 7: Delete unused files, verify build
