# Load Analyzer Monitoring Notes

## Architecture

Two separate monitors write to the same MySQL database at `ibss-central` (10.4.90.123:3312), table `processes`:

### Monitor 1: Docker container on ibss-alt (10.4.90.140)
- **Location:** `/home/jrussack/load_analyzer/monitor.py`
- **Container:** `load_analyzer_app_1` (docker-compose.yml)
- **SSH key:** jrussack's key (~/.ssh/id_rsa), connects as `admin@<host>`
- **Hosts reached:** blackburn, rudra, tdobz, kali, deepsheep, deepsquid
- **Hosts unreachable (SSH key rejected):** alice, flor, rosalindf, ibss-spark-1, dirac
- **Collects:** RSS + PSS (PSS via second SSH call using sudo + /proc/PID/smaps_rollup)

### Monitor 2: Unknown location (likely ibss-central)
- **Hosts reached:** alice, flor, rosalindf, ibss-spark-1, tdobz
- **Collects:** RSS only (old monitor version, no PSS collection)
- **Note:** tdobz gets data from BOTH monitors, causing duplicate rows with different RSS/PSS patterns

## Known Issues

### 1. .bashrc on some hosts runs the ps command on SSH login
The `admin` user on blackburn, rudra, deepsheep, kali has a `.bashrc` (or `.profile`) that executes the full `ps -e -o ...` command on every SSH login. This means:
- Every SSH command gets ~2500 lines of ps output prepended to the actual command output
- The first `ps` call from the monitor works anyway (it parses valid ps output, just duplicated)
- The second SSH call for PSS collection gets drowned — the `sudo sh -c 'for pid...'` output is buried under .bashrc noise

**Impact:** PSS collection fails on these hosts. After the insert-index fix (see below), RSS is now correctly stored, and PSS defaults to 0.

**Fix:** Remove the ps command from admin's .bashrc on blackburn, rudra, deepsheep, kali. It was likely added accidentally during testing.

### 2. Column swap bug (FIXED 2026-03-23)
`args.insert(5, pss_kb)` inserted the PSS value BEFORE RSS in the parameter list, causing:
- PSS value → `rss` column
- RSS value → `pss` column

**Fix:** Changed to `args.insert(6, pss_kb)` to insert after RSS.

**Historical data impact:** All rows written by this monitor before the fix have rss/pss swapped. The API uses `GREATEST(rss, pss)` which accidentally returns the correct value regardless. For hosts covered by Monitor 1 before the fix:
- `rss` column = actually contains the failed PSS lookup (always 0)
- `pss` column = actually contains the real RSS value

### 3. Duplicate rows for tdobz
Both monitors collect data for tdobz, resulting in ~2x the rows. Monitor 1 writes with PSS (now correctly after fix), Monitor 2 writes with RSS only.

### 4. PSS collection marker (added 2026-03-23)
Added `PSS_DATA:` prefix to PSS output lines so they can be distinguished from .bashrc noise. This works but PSS collection still fails because the .bashrc runs `ps` before `sudo` gets a chance to execute. The real fix is cleaning up the .bashrc files.

## Database Indexes (on remote MySQL at 10.4.90.123)

Added 2026-03-23:
- `idx_proc_user_time (username, snapshot_datetime)` — speeds up per-user process queries
- `idx_proc_host_pid_time (host, pid, snapshot_datetime)` — speeds up per-process timeline queries
- `idx_snapshot_datetime (snapshot_datetime)` — pre-existing

## TODO

- [ ] Find and document Monitor 2 on ibss-central
- [ ] Clean up admin's .bashrc on blackburn, rudra, deepsheep, kali (remove the ps command)
- [ ] After .bashrc fix, PSS collection should start working on those hosts
- [ ] Consider consolidating to a single monitor
- [ ] Consider deduplicating tdobz data or having only one monitor cover it
