# ConstructAI Workspaces — LLM Context Summary

> **Purpose:** Give an LLM agent enough context to understand, navigate, and contribute to this codebase.

## What This App Does

ConstructAI is a **human-in-the-loop document validation system** for construction engineering drawings. It:

1. **Ingests** PDF construction documents (structural plans, specs, schedules)
2. **Extracts** structured chunks (figures, tables, text) via LandingAI's API
3. **Classifies** chunks into 19 construction-specific subtypes via Google Gemini AI
4. **Presents** extracted data in a canvas-based validation interface
5. **Lets humans** review, edit, approve, or reject AI-extracted information

The core value proposition: AI does the heavy lifting of extraction; humans verify correctness through an intuitive UI.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Runtime | Node.js 20, TypeScript (ES Modules) |
| Backend | Express.js, modular controller/routes |
| Database | PostgreSQL 16, Drizzle ORM |
| Frontend | React 19, Vite, TanStack Query, Wouter |
| State | Zustand (complex UI) + React Context (legacy) |
| UI | shadcn/ui (Radix + Tailwind CSS v4) |
| Canvas | Fabric.js (main app), ImageCanvas (demo) |
| PDF | pdf-lib (metadata), pdftoppm (rendering), pdfjs-dist (viewing) |
| AI | LandingAI (extraction), Gemini (classification/augmentation) |
| Storage | Abstracted: local filesystem or Google Cloud Storage |
| Auth | Passport.js (HTTP Basic), bcrypt, express-session |
| Monitoring | Sentry (production only) |
| Testing | Vitest (unit + integration) |

## Directory Structure (Key Paths)

```
constructai-workspaces/
├── server/                    # Express backend
│   ├── index.ts               # Server entry point
│   ├── routes/index.ts        # Route mounting
│   ├── controllers/           # 14 domain controllers (chunks, documents, projects, etc.)
│   ├── pdfProcessor.ts        # PDF → pages → chunks pipeline
│   ├── landingAI.ts           # LandingAI API client
│   ├── storage/               # Storage abstraction (local / GCS)
│   ├── middleware/auth.ts      # Authentication
│   └── utils/                 # Logger, Gemini clients, validators
├── client/src/
│   ├── main.tsx               # React entry point
│   ├── App.tsx                # Router (legacy + demo routes)
│   ├── pages/                 # Legacy validation pages
│   ├── components/            # Shared UI components
│   └── demo/                  # Demo workspace system
│       ├── DemoApp.tsx        # Workspace tab navigation
│       ├── workspaces/        # Individual workspace implementations
│       │   ├── files/         # WS0: Project & document management
│       │   ├── extraction/    # WS1: Chunk extraction & validation
│       │   ├── plans/         # WS3: Plans & element instances (reference impl)
│       │   └── takeoff/       # WS4: Quantity takeoff
│       ├── components/        # Reusable demo components (layout, canvas, common)
│       └── data/              # Mock data (Edificio Tello detections)
├── shared/
│   ├── schema.ts              # Drizzle DB schema (source of truth)
│   └── constants.ts           # Chunk subtypes, colors, categories
├── test/                      # Vitest tests (unit + integration)
├── drizzle/                   # Generated migration SQL files
├── docs/                      # Documentation
├── PRPs/                      # Feature specs (PRP-style)
└── docker-compose.yml         # PostgreSQL + app + Adminer
```

## Database Schema (Core Tables)

| Table | Purpose | Key Columns |
|-------|---------|------------|
| `users` | Accounts | id, username, password |
| `projects` | Construction projects | id, name, clientName, status |
| `documents` | Uploaded PDFs | id, projectId, filename, status, pdfUrl, pageImageUrls |
| `pages` | Individual PDF pages | id, documentId, pageIndex, imageUrl, dimensions |
| `chunks` | Extracted elements | id, documentId, type, markdown, boundingBox, page, status, subtype, geminiDescription |
| `levels` | Floor levels | id, projectId, name, elevation |
| `elementTypes` | Element templates (C-01, B-02) | id, projectId, code, name, category |
| `elementInstances` | AI-detected instances | id, pageId, typeId, confidence, status, bbox coordinates |

**Key relationships:** Projects → Documents → Pages → ElementInstances; Projects → Levels; Projects → ElementTypes → ElementInstances; Documents → Chunks.

## API Endpoints (REST)

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/documents/upload` | Upload PDF |
| POST | `/api/documents/:id/process` | Convert PDF to page images |
| POST | `/api/documents/:id/extract` | Send to LandingAI for extraction |
| GET | `/api/documents` | List documents |
| GET/PUT/DELETE | `/api/documents/:id` | CRUD single document |
| GET/PUT/DELETE | `/api/chunks/:id` | CRUD single chunk |
| POST | `/api/chunks/:id/split` | Split chunk into sub-chunks |
| POST | `/api/chunks/:id/augment` | Trigger Gemini AI augmentation |
| GET | `/api/projects` | List projects |
| GET | `/api/pages/:id/instances` | Get element instances for a page |
| GET | `/api/health` | Health check |

## Data Flow: PDF → Validated Chunks

```
User uploads PDF
  → server/controllers/documents.controller.ts (upload handler)
  → server/pdfProcessor.ts (extract metadata, convert pages to PNGs)
  → server/landingAI.ts (send to LandingAI API, get chunks back)
  → Database: create document + page + chunk records
  → [Optional] server/utils/aiServiceClient.ts (Gemini classification)
  → Frontend: canvas-based validation UI
  → User validates/edits/approves chunks
  → PUT /api/chunks/:id (save changes)
```

## Frontend Architecture

**Two applications in one:**

1. **Legacy app** (`/` routes) — Document list, validation interface with Fabric.js canvas, chunk editing. Uses TanStack Query + React Context.

2. **Demo app** (`/demo` route) — 7-workspace navigation system. Uses Zustand stores with Immer middleware and slice composition pattern. Workspace 3 (Plans) is the **reference implementation** for building new workspaces.

**Zustand store pattern** (used in demo workspaces):
```
Store = selectionSlice + historySlice + dataSlice + uiSlice
```
Each slice manages a specific domain. Composed via `create(immer(...slices))`.

## Development Commands

```bash
npm run dev              # Local dev server (hot-reload)
npm run docker:dev       # Docker dev with hot-reload
npm run build            # Production build (Vite + esbuild)
npm test                 # All tests
npm run test:unit        # Mocked DB tests
npm run test:integration # Real PostgreSQL tests
npm run db:generate      # Generate migration from schema changes
npm run db:migrate       # Apply pending migrations
```

## Key Conventions

- **ES Modules** throughout (`"type": "module"`, `.js` extensions in imports)
- **Path aliases:** `@/*` → `client/src/*`, `@shared/*` → `shared/*`
- **Bounding boxes** use normalized coordinates (0–1 range)
- **File naming:** PascalCase for React components, camelCase for utilities
- **Controllers** contain business logic; routes just wire HTTP to controllers
- **Storage** is abstracted — `STORAGE_TYPE=local|gcs` switches backends
- **Migrations** via Drizzle Kit — never edit generated SQL, never use `db:push` in production

## External Service Dependencies

| Service | Purpose | Config |
|---------|---------|--------|
| LandingAI ADE API | PDF chunk extraction | `LANDINGAI_API_KEY` |
| Google Gemini | Chunk classification & description | `GEMINI_API_KEY` |
| Google Cloud Storage | Production file storage | `GCS_BUCKET_NAME`, `GCS_PROJECT_ID` |
| Sentry | Error monitoring (prod) | `SENTRY_DSN` |
| PostgreSQL 16 | Primary database | `DATABASE_URL` |
