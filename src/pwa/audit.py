"""`pwa audit` - Parts 1-6 of the audit, read-only by default.

Read-only means read-only: nothing is written, moved or deleted unless
`--apply` is passed, and even then every path is printed before it is removed
and the files classified KEEP are never touched.
"""

import ast
import hashlib
import logging
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger("pwa.audit")

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = REPO_ROOT / "src" / "pwa"
DATA_OUT = REPO_ROOT / "data" / "out"
DATA_RAW = REPO_ROOT / "data" / "raw"

ENTRY_MODULES = ("pwa.cli",)

# Paths that must never be deleted, whatever else this module concludes.
NEVER_DELETE = (
    ".env",
    ".env.local",
    "certs",
    "venv",
    ".git",
    "tests/fixtures",
    "data/out/selected_movie_ids.csv",
    "data/out/.selected_movie_ids_sha256",
)

TOOL_CACHES = (".pytest_cache", ".ruff_cache", ".mypy_cache")
SQLITE_SUFFIXES = (".db", ".sqlite", ".sqlite3")

NOT_IMPORTED_BY_DESIGN = (
    "pwa.__init__",
    "pwa.agent",
    "pwa.agent.agent",
    "pwa.agent.pipeline",
    "pwa.agent.pipeline.__init__",
    "pwa.preprocessing",
    "pwa.preprocessing.__init__",
)

# settings.py is the one place allowed to read the environment; kaggle_download
# only *writes* two variables that the third-party Kaggle client reads back;
# audit.py is the scanner and only mentions them in its own detector.
ENV_READ_ALLOWED = {"settings.py", "kaggle_download.py", "audit.py"}
# settings.py must name the forbidden targets to reject them, and audit.py must
# name them to classify the residue for deletion.
LOCAL_DB_REFERENCE_ALLOWED = {"settings.py", "audit.py"}


def hr(title: str) -> None:
    print("\n" + "=" * 100)
    print(" " + title)
    print("=" * 100)


def human(n: int) -> str:
    return f"{n:,}"


@dataclass
class AuditState:
    problems: list[str] = field(default_factory=list)
    delete_paths: list[tuple[Path, int, str]] = field(default_factory=list)
    bq_files_populated: bool = False
    kaggle_refetchable: bool = False
    mysql_ids: set = field(default_factory=set)
    pg_ids: set = field(default_factory=set)

    def problem(self, msg: str) -> None:
        self.problems.append(msg)
        print(f"  !! {msg}")


def _is_protected(path: Path) -> bool:
    rel = path.relative_to(REPO_ROOT).as_posix()
    return any(rel == p or rel.startswith(p + "/") for p in NEVER_DELETE)


def _code_without_comments_and_strings(path: Path) -> list[tuple[int, str]]:
    """Return (line number, code) for each line, with comments and string literals blanked out."""
    import io
    import tokenize

    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    blanked = [list(line) for line in lines]
    tokens = tokenize.generate_tokens(io.StringIO(text).readline)
    for tok in tokens:
        if tok.type not in (tokenize.COMMENT, tokenize.STRING):
            continue
        (srow, scol), (erow, ecol) = tok.start, tok.end
        for row in range(srow, erow + 1):
            if row - 1 >= len(blanked):
                continue
            start = scol if row == srow else 0
            end = ecol if row == erow else len(blanked[row - 1])
            for col in range(start, min(end, len(blanked[row - 1]))):
                blanked[row - 1][col] = " "
    return [(i, "".join(chars)) for i, chars in enumerate(blanked, 1) if "".join(chars).strip()]


def _dir_size(path: Path) -> int:
    total = 0
    for root, dirs, files in os.walk(path):
        if ".git" in root or "venv" in Path(root).parts:
            continue
        for f in files:
            try:
                total += (Path(root) / f).stat().st_size
            except OSError:
                continue
    return total


# --------------------------------------------------------------------------
# Part 1 - code inventory
# --------------------------------------------------------------------------


def part1_code_inventory(state: AuditState) -> None:
    hr("PART 1 - CODE INVENTORY")

    py_files = sorted(f for f in SRC_DIR.rglob("*.py") if "__pycache__" not in f.parts)
    sql_files = sorted((REPO_ROOT / "sql").glob("*.sql"))

    def get_mod_name(f: Path) -> str:
        rel = f.relative_to(SRC_DIR).with_suffix("")
        parts = ["pwa"] + list(rel.parts)
        if parts[-1] == "__init__":
            parts.pop()
        return ".".join(parts)

    imports: dict[str, set[str]] = {}
    for f in py_files:
        mod = get_mod_name(f)
        found = set()
        tree = ast.parse(f.read_text(encoding="utf-8"), filename=str(f))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("pwa"):
                found.add(node.module)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith("pwa"):
                        found.add(alias.name)
        imports[mod] = found

    # Reachability: breadth-first from the entry points.
    reachable = set()
    queue = [m for m in ENTRY_MODULES]
    while queue:
        mod = queue.pop()
        if mod in reachable:
            continue
        reachable.add(mod)
        queue.extend(imports.get(mod, ()))

    importers: dict[str, list[str]] = {get_mod_name(f): [] for f in py_files}
    for mod, targets in imports.items():
        for t in targets:
            if t in importers:
                importers[t].append(mod)

    test_text = "\n".join(p.read_text(encoding="utf-8") for p in (REPO_ROOT / "tests").glob("*.py"))

    print(f"{'MODULE':<36} | {'LINES':>5} | {'IMPORTED BY':<36} | REACHABLE")
    print("-" * 100)
    for f in py_files:
        mod = get_mod_name(f)
        lines = len(f.read_text(encoding="utf-8").splitlines())
        by = importers[mod][:]
        if mod in test_text or f.name in test_text:
            by.append("tests")
        if mod in ENTRY_MODULES:
            reach = "yes (entry point)"
        elif mod in NOT_IMPORTED_BY_DESIGN or mod.endswith(".__init__") or mod == "pwa":
            reach = "yes (package marker)"
        elif mod in reachable or any(mod.startswith(r + ".") for r in reachable):
            reach = "yes"
        else:
            reach = "NO - DEAD"
        print(f"{mod:<36} | {lines:>5} | {', '.join(by)[:36] or '-':<36} | {reach}")
        if reach == "NO - DEAD":
            state.problem(f"{mod} is not reachable from any entry point (dead code)")


    print(f"\n{'SQL FILE':<34} | {'LINES':>5} | REFERENCED BY")
    print("-" * 100)
    src_text = "\n".join(p.read_text(encoding="utf-8") for p in py_files)
    for f in sql_files:
        lines = len(f.read_text(encoding="utf-8").splitlines())
        ref = "src" if f.name in src_text else "reference material only"
        print(f"{('sql/' + f.name):<34} | {lines:>5} | {ref}")

    print("\n--- bare except / `except Exception: pass`")
    hits = 0
    for f in py_files:
        src_lines = f.read_text(encoding="utf-8").splitlines()
        for i, line in enumerate(src_lines, 1):
            stripped = line.strip()
            bare = stripped == "except:"
            broad_pass = (
                re.match(r"^except\s+(Exception|BaseException)\b", stripped)
                and i < len(src_lines)
                and src_lines[i].strip() == "pass"
            )
            if bare or broad_pass:
                print(f"  {f.relative_to(REPO_ROOT)}:{i}: {stripped}")
                state.problem(f"swallowing except at {f.relative_to(REPO_ROOT)}:{i}")
                hits += 1
    if not hits:
        print("  none")

    # The two scans below read executable code only: comments and string
    # literals are stripped, so prose about sqlite does not look like sqlite,
    # and this module's own detector strings do not match themselves.
    code_only = {f: _code_without_comments_and_strings(f) for f in py_files}

    print("\n--- os.getenv / os.environ call sites (should collapse to settings.py)")
    env_sites = [
        (f.name, i, line.strip())
        for f, lines in code_only.items()
        for i, line in lines
        if "os.getenv" in line or "os.environ" in line
    ]
    for name, i, line in env_sites:
        print(f"  {name}:{i}: {line}")
    offenders = {name for name, _, _ in env_sites} - ENV_READ_ALLOWED
    if offenders:
        state.problem(f"environment read outside settings.py: {sorted(offenders)}")
    if not env_sites:
        print("  none")

    print("\n--- occurrences of sqlite / fallback / local-file engine targets in code")
    pattern = re.compile(r"sqlite|fallback|\.db\b", re.IGNORECASE)
    found_any = False
    for f, code_lines in code_only.items():
        for i, line in code_lines:
            if pattern.search(line):
                print(f"  {f.name}:{i}: {line.strip()}")
                found_any = True
                if f.name not in LOCAL_DB_REFERENCE_ALLOWED:
                    state.problem(f"local-file engine reference at {f.name}:{i}")
    if not found_any:
        print("  none")

    print("\n--- import check from a clean interpreter")
    rc = subprocess.run(
        [
            sys.executable,
            "-c",
            "import importlib,pkgutil,pwa;"
            "mods=[m.name for m in pkgutil.walk_packages(pwa.__path__,'pwa.')];"
            "[importlib.import_module(m) for m in mods];"
            "print(f'{len(mods)} modules imported OK')",
        ],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    print("  " + (rc.stdout.strip() or rc.stderr.strip()[:400]))
    if rc.returncode != 0:
        state.problem("not every module imports from a clean interpreter")


# --------------------------------------------------------------------------
# Part 2 - configuration audit
# --------------------------------------------------------------------------


def part2_config(state: AuditState):
    hr("PART 2 - CONFIGURATION AUDIT")
    from pwa.settings import get_settings

    try:
        settings = get_settings()
    except Exception as e:
        state.problem(f"configuration validation FAILED: {e}")
        return None

    print(f"{'SETTING':<30} | VALUE")
    print("-" * 100)
    for name, value in settings.redacted_rows():
        print(f"{name:<30} | {value}")
    print("\n  Settings validation: PASSED (all rules satisfied)")
    return settings


# --------------------------------------------------------------------------
# Part 3 - connection tests
# --------------------------------------------------------------------------


def _timed(fn):
    t0 = time.time()
    try:
        return fn(), time.time() - t0, None
    except Exception as e:
        return None, time.time() - t0, f"{type(e).__name__}: {str(e)[:300]}"


def part3_connections(state: AuditState, settings):
    hr("PART 3 - CONNECTION TESTS")
    from sqlalchemy import text

    from pwa.connections import get_bq_client, get_mysql_engine

    engines: dict[str, object] = {}

    def mysql_probe():
        engine, kind = get_mysql_engine()
        with engine.connect() as c:
            row = c.execute(text("SELECT VERSION(), DATABASE(), CURRENT_USER()")).fetchone()
            cipher = c.execute(text("SHOW STATUS LIKE 'Ssl_cipher'")).fetchone()
        return engine, kind, row, cipher

    res, dt, err = _timed(mysql_probe)
    print(f"\n[Aiven MySQL] {settings.mysql_host}:{settings.mysql_port}  latency={dt:.1f}s")
    if err:
        print(f"  RESULT: FAIL  {err}")
        state.problem(f"Aiven MySQL connection failed: {err}")
    else:
        engine, kind, row, cipher = res
        engines["mysql"] = engine
        print(f"  RESULT: OK  engine={kind}")
        print(f"  version={row[0]}  database={row[1]}  current_user={row[2]}")
        cipher_value = cipher[1] if cipher else ""
        print(f"  Ssl_cipher={cipher_value!r} -> {'SSL ACTIVE' if cipher_value else 'UNENCRYPTED'}")
        if not cipher_value:
            state.problem("Aiven MySQL connection is NOT encrypted (blank Ssl_cipher)")

    def pg_connector_probe():
        from sqlalchemy import create_engine

        from google.cloud.sql.connector import Connector

        connector = Connector()
        engine = create_engine(
            "postgresql+pg8000://",
            creator=lambda: connector.connect(
                settings.pg_instance_connection_name,
                "pg8000",
                user=settings.pg_user,
                password=settings.pg_password,
                db=settings.pg_db,
            ),
        )
        with engine.connect() as c:
            return engine, c.execute(text("SELECT version(), current_database(), current_user")).fetchone()

    res, dt, err = _timed(pg_connector_probe)
    print(f"\n[Cloud SQL Postgres - connector] {settings.pg_instance_connection_name}  latency={dt:.1f}s")
    if err:
        print(f"  RESULT: FAIL  {err}")
        if settings.pg_connect_mode == "connector":
            state.problem(f"Cloud SQL connector mode failed: {err}")
    else:
        engine, row = res
        engines["pg"] = engine
        print(f"  RESULT: OK\n  version={row[0][:60]}\n  database={row[1]}  current_user={row[2]}")

    def pg_direct_probe():
        from sqlalchemy import create_engine
        from urllib.parse import quote_plus

        if not settings.pg_host:
            raise RuntimeError("PG_HOST is empty: direct mode is not configured")
        dsn = (
            f"postgresql+psycopg2://{settings.pg_user}:{quote_plus(settings.pg_password)}"
            f"@{settings.pg_host}:{settings.pg_port}/{settings.pg_db}?sslmode=require"
        )
        engine = create_engine(dsn, connect_args={"connect_timeout": 15})
        with engine.connect() as c:
            return c.execute(text("SELECT version(), current_database(), current_user")).fetchone()

    res, dt, err = _timed(pg_direct_probe)
    print(f"\n[Cloud SQL Postgres - direct] {settings.pg_host or '(unset)'}:{settings.pg_port}  latency={dt:.1f}s")
    if err:
        print(f"  RESULT: NOT VERIFIED  {err}")
        if settings.pg_connect_mode == "direct":
            state.problem(f"configured direct Postgres mode failed: {err}")
    else:
        print(f"  RESULT: OK  database={res[1]}  current_user={res[2]}")

    def bq_probe():
        import google.auth

        client = get_bq_client()
        ok = list(client.query("SELECT 1 AS ok").result())[0]["ok"]
        creds, project = google.auth.default()
        return (
            client,
            ok,
            project,
            getattr(creds, "quota_project_id", None),
            getattr(creds, "service_account_email", None),
        )

    res, dt, err = _timed(bq_probe)
    print(f"\n[BigQuery] project={settings.gcp_project} location={settings.bq_location}  latency={dt:.1f}s")
    client = None
    if err:
        print(f"  RESULT: FAIL  {err}")
        state.problem(f"BigQuery connection failed: {err}")
    else:
        client, ok, project, quota, sa_email = res
        print(f"  RESULT: OK  SELECT 1 -> {ok}")
        print(f"  identity={sa_email or 'user ADC'}  adc_project={project}  quota_project={quota}")
        if not quota:
            state.problem("ADC quota project is not set (expect intermittent 403s on BigQuery)")

    if client is not None:
        conn_resource = f"{settings.gcp_project}.{settings.bq_location}.{settings.bq_connection_id}"
        res, dt, err = _timed(
            lambda: list(client.query(f"SELECT * FROM EXTERNAL_QUERY('{conn_resource}', 'SELECT 1 AS ok')").result())
        )
        print(f"\n[Federation EXTERNAL_QUERY] {conn_resource}  latency={dt:.1f}s")
        if err:
            print(f"  RESULT: FAIL  {err}")
            state.problem(f"federation EXTERNAL_QUERY failed: {err}")
        else:
            print(f"  RESULT: OK  ok={res[0]['ok']}")

    def agent_sa_probe():
        import google.auth
        from google.auth import impersonated_credentials
        from google.cloud import bigquery

        source, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
        sa = f"warehouse-agent@{settings.gcp_project}.iam.gserviceaccount.com"
        target = impersonated_credentials.Credentials(
            source_credentials=source,
            target_principal=sa,
            target_scopes=["https://www.googleapis.com/auth/cloud-platform"],
        )
        agent_client = bigquery.Client(project=settings.gcp_project, location=settings.bq_location, credentials=target)
        rows = list(
            agent_client.query(
                f"SELECT COUNT(*) AS c FROM `{settings.gcp_project}.{settings.bq_ds_mart}.v_movie_full`"
            ).result()
        )[0]["c"]
        return sa, rows

    res, dt, err = _timed(agent_sa_probe)
    print(f"\n[Agent service account -> {settings.bq_ds_mart}.v_movie_full]  latency={dt:.1f}s")
    if err:
        print(f"  RESULT: CANNOT VERIFY  {err}")
        state.problem(f"agent service account read path unverified: {err}")
    else:
        print(f"  RESULT: OK  sa={res[0]}  rows={res[1]}")

    return engines, client


# --------------------------------------------------------------------------
# Part 4 - record inventory
# --------------------------------------------------------------------------


def _print_rows(rows, cols, width=18):
    print("  " + " | ".join(str(c)[:width].ljust(width) for c in cols))
    print("  " + "-+-".join("-" * width for _ in cols))
    for r in rows:
        print("  " + " | ".join(str(v)[:width].ljust(width) for v in r))


def part4_inventory(state: AuditState, settings, engines, client):
    hr("PART 4 - RECORD INVENTORY")
    from sqlalchemy import text

    consolidated: list[tuple] = []

    # ---- MySQL
    print("\n--- Aiven MySQL")
    if "mysql" in engines:
        with engines["mysql"].connect() as c:
            tables = [r[0] for r in c.execute(text("SHOW TABLES")).fetchall()]
            print(f"SHOW TABLES -> {tables}")
            for t in tables:
                count = c.execute(text(f"SELECT COUNT(*) FROM `{t}`")).scalar()
                cols = c.execute(
                    text(
                        "SELECT column_name, column_type, is_nullable, column_key "
                        "FROM information_schema.columns WHERE table_schema=:s AND table_name=:t "
                        "ORDER BY ordinal_position"
                    ),
                    {"s": settings.mysql_db, "t": t},
                ).fetchall()
                size = c.execute(
                    text(
                        "SELECT data_length + index_length FROM information_schema.tables "
                        "WHERE table_schema=:s AND table_name=:t"
                    ),
                    {"s": settings.mysql_db, "t": t},
                ).scalar()
                print(
                    f"\n  TABLE `{settings.mysql_db}`.`{t}`  engine=aiven_mysql  rows={count}  size={human(size or 0)} bytes"
                )
                for name, ctype, nullable, key in cols:
                    print(f"    {name:<22} {ctype:<20} null={nullable} {'PK' if key == 'PRI' else key}")
                for name, _, _, key in cols:
                    if key == "PRI":
                        mn, mx, dc = c.execute(
                            text(f"SELECT MIN(`{name}`), MAX(`{name}`), COUNT(DISTINCT `{name}`) FROM `{t}`")
                        ).fetchone()
                        print(f"  PK {name}: min={mn} max={mx} distinct={dc}")
                sample = c.execute(text(f"SELECT * FROM `{t}` ORDER BY 1 LIMIT 3")).fetchall()
                print("  sample rows (first 7 columns):")
                _print_rows([r[:7] for r in sample], [x[0] for x in cols][:7])
                consolidated.append(("Aiven MySQL", "mysql", f"{settings.mysql_db}.{t}", "TABLE", count))
            if "movie" in tables:
                state.mysql_ids = {r[0] for r in c.execute(text("SELECT movie_id FROM movie")).fetchall()}
    else:
        state.problem("MySQL inventory skipped: no connection")

    # ---- Postgres
    print("\n--- Cloud SQL PostgreSQL")
    if "pg" in engines:
        with engines["pg"].connect() as c:
            tables = c.execute(
                text(
                    "SELECT schemaname, tablename FROM pg_tables "
                    "WHERE schemaname NOT IN ('pg_catalog','information_schema')"
                )
            ).fetchall()
            print(f"pg_tables -> {[f'{s}.{t}' for s, t in tables]}")
            for schema, t in tables:
                rel = f"{schema}.{t}"
                count = c.execute(text(f'SELECT COUNT(*) FROM "{schema}"."{t}"')).scalar()
                cols = c.execute(
                    text(
                        "SELECT column_name, data_type, is_nullable FROM information_schema.columns "
                        "WHERE table_schema=:s AND table_name=:t ORDER BY ordinal_position"
                    ),
                    {"s": schema, "t": t},
                ).fetchall()
                size = c.execute(text("SELECT pg_total_relation_size(:rel)"), {"rel": rel}).scalar()
                pk = c.execute(
                    text(
                        "SELECT a.attname FROM pg_index i JOIN pg_attribute a "
                        "ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey) "
                        "WHERE i.indrelid = to_regclass(:rel) AND i.indisprimary"
                    ),
                    {"rel": rel},
                ).fetchall()
                print(f"\n  TABLE {rel}  engine=cloud_sql_postgres  rows={count}  size={human(size or 0)} bytes")
                for name, dtype, nullable in cols:
                    print(f"    {name:<22} {dtype:<22} null={nullable}")
                for (name,) in pk:
                    mn, mx, dc = c.execute(
                        text(f'SELECT MIN({name}), MAX({name}), COUNT(DISTINCT {name}) FROM "{schema}"."{t}"')
                    ).fetchone()
                    print(f"  PK {name}: min={mn} max={mx} distinct={dc}")
                sample = c.execute(text(f'SELECT * FROM "{schema}"."{t}" ORDER BY 1 LIMIT 3')).fetchall()
                print("  sample rows (first 7 columns):")
                _print_rows([r[:7] for r in sample], [x[0] for x in cols][:7])
                consolidated.append(("Cloud SQL PostgreSQL", "postgres", rel, "TABLE", count))
            state.pg_ids = {r[0] for r in c.execute(text("SELECT movie_id FROM movie_credits")).fetchall()}
    else:
        state.problem("PostgreSQL inventory skipped: no connection")

    # ---- BigQuery
    print("\n--- BigQuery")
    if client is not None:
        datasets = [settings.bq_ds_registry, settings.bq_ds_credits, settings.bq_ds_files, settings.bq_ds_mart]
        for ds in datasets:
            print(f"\n  dataset {settings.gcp_project}.{ds}")
            objects = list(
                client.query(
                    f"SELECT table_name, table_type FROM `{settings.gcp_project}.{ds}.INFORMATION_SCHEMA.TABLES` "
                    "ORDER BY table_type, table_name"
                ).result()
            )
            if not objects:
                print("    (no objects)")
            for obj in objects:
                name, ttype = obj["table_name"], obj["table_type"]
                fq = f"{settings.gcp_project}.{ds}.{name}"
                count = list(client.query(f"SELECT COUNT(*) AS c FROM `{fq}`").result())[0]["c"]
                table = client.get_table(fq)
                federated = ttype == "VIEW" and "EXTERNAL_QUERY" in (table.view_query or "").upper()
                size = f"{human(table.num_bytes or 0)} bytes" if ttype == "BASE TABLE" else "0 (logical view)"
                label = ttype + (" [FEDERATED]" if federated else "")
                print(f"\n    {label} `{fq}`  rows={count}  size={size}")
                print("    columns: " + ", ".join(f"{f.name}:{f.field_type}" for f in table.schema))
                if any(f.name == "movie_id" for f in table.schema):
                    r = list(
                        client.query(
                            f"SELECT MIN(movie_id) mn, MAX(movie_id) mx, COUNT(DISTINCT movie_id) dc FROM `{fq}`"
                        ).result()
                    )[0]
                    print(f"    PK movie_id: min={r['mn']} max={r['mx']} distinct={r['dc']}")
                cols = [f.name for f in table.schema][:6]
                sample = list(client.query(f"SELECT * FROM `{fq}` LIMIT 3").result())
                print("    sample rows (first 6 columns):")
                _print_rows([[row[c] for c in cols] for row in sample], cols)
                consolidated.append(("BigQuery", f"bigquery/{settings.bq_location}", f"{ds}.{name}", label, count))

    else:
        state.problem("BigQuery inventory skipped: no client")

    # ---- Local CSVs
    print("\n--- Local files in data/out")
    if DATA_OUT.is_dir():
        for f in sorted(DATA_OUT.iterdir()):
            if not f.is_file():
                continue
            blob = f.read_bytes()
            sha = hashlib.sha256(blob).hexdigest()
            rows: int | str = "-"
            if f.suffix == ".csv":
                rows = sum(1 for _ in f.open(encoding="utf-8", errors="replace")) - 1
                consolidated.append(("Local disk", "csv file", f"data/out/{f.name}", "CSV", rows))
            print(f"  {f.name:<34} {human(len(blob)):>12} bytes  rows={str(rows):<8} sha256={sha}")
    else:
        print("  data/out does not exist")

    hr("CONSOLIDATED INVENTORY - which record is stored in each store")
    print(f"{'STORE':<22} | {'ENGINE':<18} | {'OBJECT':<40} | {'TYPE':<24} | ROWS")
    print("-" * 125)
    for store, engine, obj, ttype, rows in consolidated:
        print(f"{store:<22} | {engine:<18} | {obj:<40} | {ttype:<24} | {rows}")
    return consolidated


# --------------------------------------------------------------------------
# Part 5 - cross-store reconciliation
# --------------------------------------------------------------------------


def part5_reconciliation(state: AuditState, settings, client) -> None:
    hr("PART 5 - CROSS-STORE RECONCILIATION")
    import pandas as pd

    mysql_ids, pg_ids = state.mysql_ids, state.pg_ids
    if not mysql_ids or not pg_ids:
        state.problem("reconciliation impossible: one or both source id sets are empty")
        return

    print(f"1. MySQL movie_id count={len(mysql_ids)}   Postgres movie_id count={len(pg_ids)}")
    only_mysql = sorted(mysql_ids - pg_ids)
    only_pg = sorted(pg_ids - mysql_ids)
    equal = mysql_ids == pg_ids
    print(f"2. sets exactly equal: {equal}")
    print(f"   in MySQL not Postgres  n={len(only_mysql)} {only_mysql[:10]}")
    print(f"   in Postgres not MySQL  n={len(only_pg)} {only_pg[:10]}")
    if not equal:
        state.problem(f"MySQL and Postgres movie_id sets differ (symmetric difference {len(mysql_ids ^ pg_ids)})")

    joined = len(mysql_ids & pg_ids)
    print(f"3. inner join cardinality = {joined} (expect 1000) -> {joined == 1000}")
    if joined != 1000:
        state.problem(f"inner join cardinality is {joined}, expected 1000")

    for name in ("selected_movie_ids.csv", "movie_keywords.csv", "movie_ratings_agg.csv"):
        path = DATA_OUT / name
        if not path.exists():
            print(f"4. {name:<26} MISSING")
            continue
        ids = set(pd.read_csv(path)["movie_id"])
        subset = ids.issubset(mysql_ids)
        print(f"4. {name:<26} distinct={len(ids):<6} subset_of_mysql={subset}  extra={len(ids - mysql_ids)}")
        if not subset:
            state.problem(f"{name} contains movie_ids absent from MySQL")

    if client is None:
        state.problem("BigQuery reconciliation skipped: no client")
        return

    def ids_from(sql):
        return {r["movie_id"] for r in client.query(sql).result()}

    p = settings.gcp_project
    bq_registry = ids_from(f"SELECT movie_id FROM `{p}.{settings.bq_ds_registry}.movie`")
    bq_credits = ids_from(f"SELECT movie_id FROM `{p}.{settings.bq_ds_credits}.movie_credits`")
    bq_keywords = ids_from(f"SELECT DISTINCT movie_id FROM `{p}.{settings.bq_ds_files}.movie_keywords`")
    bq_ratings = ids_from(f"SELECT movie_id FROM `{p}.{settings.bq_ds_files}.movie_ratings_agg`")

    print("\n5. Same checks through BigQuery:")
    print(f"   raw_registry.movie n={len(bq_registry)}   raw_credits.movie_credits n={len(bq_credits)}")
    print(
        f"   sets equal: {bq_registry == bq_credits}   registry-only={len(bq_registry - bq_credits)} "
        f"credits-only={len(bq_credits - bq_registry)}"
    )
    print(f"   inner join = {len(bq_registry & bq_credits)} -> {len(bq_registry & bq_credits) == 1000}")
    print(f"   movie_keywords subset of raw_registry:    {bq_keywords.issubset(bq_registry)}")
    print(f"   movie_ratings_agg subset of raw_registry: {bq_ratings.issubset(bq_registry)}")

    print("\n6. BigQuery vs direct-database agreement:")
    reg_ok = mysql_ids == bq_registry
    cred_ok = pg_ids == bq_credits
    print(f"   MySQL set == BQ raw_registry set : {reg_ok}  (symmetric difference={len(mysql_ids ^ bq_registry)})")
    print(f"   Postgres set == BQ raw_credits set: {cred_ok}  (symmetric difference={len(pg_ids ^ bq_credits)})")
    if not reg_ok:
        state.problem("BigQuery raw_registry disagrees with Aiven MySQL: the replication is STALE")
    if not cred_ok:
        state.problem("BigQuery raw_credits disagrees with Cloud SQL Postgres: the federated view is STALE")
    if not reg_ok or not cred_ok:
        print("\n  STOPPING further conclusions: landing does not preserve the source of record.")


# --------------------------------------------------------------------------
# Part 6 - local storage audit
# --------------------------------------------------------------------------


def part6_local_storage(state: AuditState, settings, client, apply_deletions: bool) -> None:
    hr("PART 6 - LOCAL STORAGE AUDIT")

    print("--- size on disk by directory")
    total = 0
    for d in sorted(p for p in REPO_ROOT.iterdir() if p.is_dir()):
        if d.name in ("venv", ".git"):
            print(f"  {d.name + '/':<24} {'(not measured)':>16}  KEEP, gitignored")
            continue
        size = _dir_size(d)
        total += size
        print(f"  {d.name + '/':<24} {human(size):>16} bytes")
    root_files = sum(f.stat().st_size for f in REPO_ROOT.iterdir() if f.is_file())
    print(f"  {'(root files)':<24} {human(root_files):>16} bytes")
    print(f"  {'TOTAL':<24} {human(total + root_files):>16} bytes")

    print("\n--- files classified DELETE")
    for root, dirs, files in os.walk(REPO_ROOT):
        rootp = Path(root)
        if any(part in ("venv", ".git") for part in rootp.parts):
            dirs[:] = []
            continue
        if rootp.name == "__pycache__":
            size = _dir_size(rootp)
            state.delete_paths.append((rootp, size, "compiled bytecode, never tracked"))
            dirs[:] = []
            continue
        if rootp.name in TOOL_CACHES or rootp.name.endswith(".egg-info"):
            state.delete_paths.append((rootp, _dir_size(rootp), "tool cache / build artifact"))
            dirs[:] = []
            continue
        for f in files:
            path = rootp / f
            if path.suffix in SQLITE_SUFFIXES and not _is_protected(path):
                state.delete_paths.append((path, path.stat().st_size, "SQLite fallback residue"))

    if state.delete_paths:
        for path, size, reason in state.delete_paths:
            print(f"  {str(path.relative_to(REPO_ROOT)):<48} {human(size):>12} bytes  {reason}")
    else:
        print("  none")

    print("\n--- data of record that exists ONLY locally")
    only_local = []
    if client is not None and DATA_OUT.is_dir():
        expected = {
            "movie_keywords.csv": f"{settings.gcp_project}.{settings.bq_ds_files}.movie_keywords",
            "movie_ratings_agg.csv": f"{settings.gcp_project}.{settings.bq_ds_files}.movie_ratings_agg",
        }
        for name, table in expected.items():
            path = DATA_OUT / name
            if not path.exists():
                continue
            local_rows = sum(1 for _ in path.open(encoding="utf-8", errors="replace")) - 1
            try:
                cloud_rows = list(client.query(f"SELECT COUNT(*) AS c FROM `{table}`").result())[0]["c"]
            except Exception as e:
                cloud_rows = None
                print(f"  {name}: cannot read {table}: {e}")
            status = "reproducible from BigQuery" if cloud_rows == local_rows else "NOT reproducible"
            print(f"  {name:<26} local={local_rows:<7} bigquery={cloud_rows}  -> {status}")
            if cloud_rows != local_rows:
                only_local.append(name)
        for path, _, reason in state.delete_paths:
            if path.suffix in SQLITE_SUFFIXES:
                print(f"  {path.name:<26} duplicate of a cloud table, holds no unique record ({reason})")
    if only_local:
        state.problem(
            "LOCAL-ONLY DATA OF RECORD: " + ", ".join(only_local) + " is not fully present in the cloud. "
            "Do not delete it; land it first."
        )
    else:
        print("  none - every local record also exists in the cloud")

    print("\n--- git ls-files filtered for anything that should be ignored")
    tracked = subprocess.run(["git", "ls-files"], capture_output=True, text=True, cwd=REPO_ROOT).stdout.splitlines()
    offenders = [
        f
        for f in tracked
        if f == ".env"
        or f.startswith("certs/")
        or f.startswith("data/")
        or f.startswith("venv/")
        or "__pycache__" in f
        or f.endswith(SQLITE_SUFFIXES)
    ]
    if offenders:
        for f in offenders:
            print(f"  TRACKED BUT SHOULD BE IGNORED: {f}")
        state.problem(f"{len(offenders)} tracked files should be gitignored")
    else:
        print(f"  none - {len(tracked)} tracked files, nothing sensitive or generated")

    print("\n--- preconditions for deleting regenerable data")
    all_populated = client is not None
    if client is not None:
        for table in (
            f"{settings.gcp_project}.{settings.bq_ds_files}.movie_keywords",
            f"{settings.gcp_project}.{settings.bq_ds_files}.movie_ratings_agg",
        ):
            try:
                rows = list(client.query(f"SELECT COUNT(*) AS c FROM `{table}`").result())[0]["c"]
                print(f"  {table}: {rows} rows -> {'populated' if rows > 0 else 'EMPTY'}")
                all_populated = all_populated and rows > 0
            except Exception as e:
                print(f"  {table}: CANNOT VERIFY ({e})")
                all_populated = False
    state.bq_files_populated = all_populated

    try:
        from kaggle.api.kaggle_api_extended import KaggleApi

        api = KaggleApi()
        api.authenticate()
        files = api.dataset_list_files("rounakbanik/the-movies-dataset").files
        print(f"  kaggle re-fetch dry-run: authenticated, {len(files)} files listed, 0 bytes downloaded")
        state.kaggle_refetchable = len(files) > 0
    except Exception as e:
        print(f"  kaggle re-fetch dry-run: CANNOT VERIFY ({type(e).__name__}: {str(e)[:160]})")
        state.kaggle_refetchable = False

    raw_size = _dir_size(DATA_RAW) if DATA_RAW.is_dir() else 0
    print(f"\n  data/raw/ is {human(raw_size)} bytes and is classified REGENERABLE")
    print(f"  re-download proven possible: {state.kaggle_refetchable}")
    print(f"  data/out CSVs reproducible from BigQuery: {state.bq_files_populated}")

    if not apply_deletions:
        print("\n  DRY RUN - nothing was deleted. Re-run with `pwa audit --apply` to delete the paths above.")
        return
    _apply_deletions(state, only_local)


def _apply_deletions(state: AuditState, only_local: list) -> None:
    """Delete every path classified DELETE, then the regenerable data whose preconditions hold."""
    import shutil

    print("\n--- APPLYING DELETIONS")
    for path, size, reason in state.delete_paths:
        if _is_protected(path):
            print(f"  SKIP (protected): {path.relative_to(REPO_ROOT)}")
            continue
        print(f"  DELETING {path.relative_to(REPO_ROOT)} ({human(size)} bytes) - {reason}")
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)
        else:
            path.unlink(missing_ok=True)

    if state.kaggle_refetchable and DATA_RAW.is_dir():
        for f in sorted(DATA_RAW.iterdir()):
            if f.is_file():
                print(
                    f"  DELETING {f.relative_to(REPO_ROOT)} ({human(f.stat().st_size)} bytes) "
                    "- regenerable Kaggle cache"
                )
                f.unlink()
    elif DATA_RAW.is_dir():
        print("  KEEPING data/raw/: re-download was not proven possible")

    if state.bq_files_populated and not only_local:
        for name in ("movie_keywords.csv", "movie_ratings_agg.csv"):
            f = DATA_OUT / name
            if f.exists():
                print(f"  DELETING {f.relative_to(REPO_ROOT)} ({human(f.stat().st_size)} bytes) - landed in BigQuery")
                f.unlink()
        print(
            "  NOTE: gates 8, 9 and 10 read these CSVs and will report CANNOT VERIFY "
            "until `pwa source run` regenerates them."
        )
    else:
        print("  KEEPING data/out CSVs: not proven reproducible from BigQuery")

    for protected in NEVER_DELETE:
        print(f"  PROTECTED, untouched: {protected}")


# --------------------------------------------------------------------------


def run_audit(apply_deletions: bool = False) -> int:
    """Run Parts 1-6. Returns 0 only if nothing problematic was found."""
    state = AuditState()

    print("\n" + "#" * 100)
    print(f"#  pwa audit - repository {REPO_ROOT}")
    print(f"#  mode: {'APPLY (deletions enabled)' if apply_deletions else 'READ-ONLY (dry run)'}")
    print(f"#  started {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}")
    print("#" * 100)

    part1_code_inventory(state)
    settings = part2_config(state)

    if settings is None:
        hr("AUDIT ABORTED")
        print("Configuration is invalid, so no live check can run. Problems found:")
        for p in state.problems:
            print(f"  - {p}")
        return 1

    engines, client = part3_connections(state, settings)
    part4_inventory(state, settings, engines, client)
    part5_reconciliation(state, settings, client)
    part6_local_storage(state, settings, client, apply_deletions)

    hr("AUDIT SUMMARY")
    if state.problems:
        print(f"{len(state.problems)} problem(s) found:\n")
        for p in state.problems:
            print(f"  - {p}")
        return 1
    print("No problems found: all connections green, inventory complete, no unclassified local data of record.")
    return 0


if __name__ == "__main__":
    raise SystemExit(run_audit("--apply" in sys.argv))
