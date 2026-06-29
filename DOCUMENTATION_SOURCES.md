# Documentation Source-of-Truth Policy

**Created:** 2026-06-28  
**Purpose:** Clarify which sources are authoritative for different types of information
**Status:** **TEMPORARY** — This file serves as a pointer while AGENTS.md encoding is corrupted

**Note:** AGENTS.md encoding repair is a separate documentation-maintenance task, not a feature prerequisite. Once AGENTS.md is repaired, this file may be archived or removed.

---

## Git is Authoritative for Repository State

**Always run these commands to determine current state:**
```powershell
git status                    # Current branch, working tree state
git log -1 --format='%H %s'  # Current HEAD commit
git branch --show-current     # Current branch name
```

Git commands are the **single source of truth** for:
- Current HEAD commit hash
- Current branch name
- Working tree state (clean, modified, untracked files)
- Commit history

---

## Documentation Files Are Baselines, Not Live State

### PROJECT_STATUS.md
- **Purpose:** Records last verified baseline
- **IS authoritative for:** Last verified test count, completed features, known limitations
- **NOT authoritative for:** Current HEAD (use `git log`), current branch (use `git status`), current working tree
- **Update policy:** After significant changes or milestones

### NEXT_TASK.md
- **Purpose:** Describes intended next task
- **IS authoritative for:** What work should be done next
- **NOT authoritative for:** What has been completed (see PROJECT_STATUS.md)
- **Update policy:** When switching tasks

### AGENTS.md
- **Purpose:** Quick-start guide for AI agents and engineers
- **IS authoritative for:** Reading order, invariants, standard commands, Definition of Done
- **NOT authoritative for:** Current repository state
- **Note:** File currently has UTF-8 encoding issues requiring repair

### README.md
- **Purpose:** User onboarding and setup instructions
- **IS authoritative for:** Installation steps, how to run application
- **NOT authoritative for:** Current development status (see PROJECT_STATUS.md)

### docs/DECISIONS.md
- **Purpose:** Architectural Decision Records (ADRs)
- **IS authoritative for:** Why certain design choices were made
- **NOT authoritative for:** What is currently implemented (see PROJECT_STATUS.md)

### docs/DATA_MODEL.md
- **Purpose:** Schema concepts and relationships
- **IS authoritative for:** Entity descriptions, state machines, immutability rules
- **NOT authoritative for:** Current schema version (run Doctor or check migrations)

### ARCHITECTURE.md
- **Purpose:** System design reference
- **Warning:** Contains historical "proposed" sections now implemented
- **IS authoritative for:** Component interactions, data flow diagrams
- **NOT authoritative for:** Feature implementation status (see PROJECT_STATUS.md)

---

## Runtime Facts Require Verification

### Database Schema Version
**Check with:**
```powershell
# Run Doctor
& 'D:\Youtube\VieNeu-TTS\.venv\Scripts\python.exe' scripts\doctor.py

# Or query directly
sqlite3 data\app.db "SELECT version FROM schema_migrations ORDER BY version DESC LIMIT 1;"
```

### Test Count
**Check with:**
```powershell
$env:PYTHONUTF8='1'
& 'D:\Youtube\VieNeu-TTS\.venv\Scripts\python.exe' -m unittest discover -s tests -v
```

### Custom Voice Assignments
**Check with:**
```powershell
# Query live database
sqlite3 data\app.db "SELECT id, display_name, is_active, preferred_synthesis_revision_id FROM custom_voices;"

# Or use API
curl http://localhost:8766/api/custom-voices
```

---

## External Project Notes

**Location:** `D:\Youtube\project_notes\Story Trans And Audio\`

**Status:** External notes are **historical evidence** unless explicitly marked CURRENT. Repository canonical documents and Git state take precedence.

**When to read:**
- Only for forensic investigation of past incidents
- Only after reading repository canonical docs first
- Never for current HEAD, branch, schema, or test count

**Note:** External notes directory is outside workspace and cannot be indexed automatically. Human review required.

---

## Reading Order for New AI Agents

1. **Run Git commands** (see above)
2. Read `PROJECT_STATUS.md` (last verified baseline)
3. Read `NEXT_TASK.md` (intended next work)
4. Read `AGENTS.md` (invariants and commands) — **requires encoding repair**
5. Read relevant sections of other docs as needed

---

## Known Issues

### AGENTS.md Encoding Corruption
- **Issue:** File has UTF-8 BOM and double-encoding corruption
- **Impact:** Content is readable but str_replace operations fail
- **Workaround:** Read content manually, or use external text editor to repair
- **Recommended fix:** Re-save file with proper UTF-8 encoding (no BOM)

---

**END OF POLICY**
