#!/usr/bin/env python3
"""Watchdog: detect stale datasets, auto-retry transient failures, alert on persistent ones."""

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

MAX_RETRIES = 2
GRACE_DAYS = 1
NO_RETRY = {"tle-history"}
SKIP_WORKFLOWS = {"readme-stats"}

ROOT = Path(__file__).resolve().parent.parent
STATUS_FILE = ROOT / "status.json"
RETRY_STATE_FILE = ROOT / "data" / "retry-state.json"
WORKFLOWS_DIR = ROOT / ".github" / "workflows"


# ---------------------------------------------------------------------------
# Cron parsing
# ---------------------------------------------------------------------------

def parse_cron_period(cron_expr: str) -> int:
    """Return the expected period in days for a 5-field cron expression."""
    fields = cron_expr.strip().split()
    if len(fields) != 5:
        return 1  # fallback to daily
    _minute, _hour, dom, month, dow = fields

    # Day-of-week specific (e.g. '1' = Monday) → weekly
    if dow != "*":
        return 7

    # Month field limited (quarterly / semi-annual / annual)
    if month != "*":
        # Count how many months are listed
        if "," in month:
            n_months = len(month.split(","))
        elif "/" in month:
            # */3 → 4 times/year, */6 → 2 times/year
            step = int(month.split("/")[1])
            n_months = max(1, 12 // step)
        else:
            n_months = 1  # single month → annual
        return max(1, 366 // n_months)

    # Day-of-month specific (e.g. '1') but month is * → monthly
    if dom != "*" and dom.isdigit():
        return 31

    # Everything else → daily
    return 1


# ---------------------------------------------------------------------------
# Load data
# ---------------------------------------------------------------------------

def load_workflow_schedules() -> dict[str, int]:
    """Parse workflow YAML files and return {dataset_name: period_days}."""
    schedules = {}
    for path in sorted(WORKFLOWS_DIR.glob("update-*.yml")):
        name = path.stem.removeprefix("update-")
        if name in SKIP_WORKFLOWS:
            continue
        text = path.read_text()
        match = re.search(r"cron:\s*'([^']+)'", text)
        if match:
            schedules[name] = parse_cron_period(match.group(1))
    return schedules


def load_status() -> dict[str, str]:
    """Load status.json and return {dataset_name: 'YYYY-MM-DD'} (skip _rows)."""
    data = json.loads(STATUS_FILE.read_text())
    return {k: v for k, v in data.items() if not k.startswith("_")}


def load_retry_state() -> dict:
    """Load retry state from file, or return empty dict."""
    if RETRY_STATE_FILE.exists():
        return json.loads(RETRY_STATE_FILE.read_text())
    return {}


def save_retry_state(state: dict) -> None:
    """Write retry state to file."""
    RETRY_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    RETRY_STATE_FILE.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")


# ---------------------------------------------------------------------------
# Staleness detection
# ---------------------------------------------------------------------------

def find_stale(schedules: dict[str, int], status: dict[str, str]) -> list[str]:
    """Return dataset names that are overdue based on their schedule."""
    today = date.today()
    stale = []
    for name, period_days in schedules.items():
        last_updated = status.get(name)
        if last_updated is None:
            stale.append(name)  # never succeeded
            continue
        last_date = date.fromisoformat(last_updated)
        threshold = timedelta(days=period_days + GRACE_DAYS)
        if today - last_date > threshold:
            stale.append(name)
    return sorted(stale)


# ---------------------------------------------------------------------------
# GitHub interaction (via gh CLI)
# ---------------------------------------------------------------------------

def gh(*args: str) -> str:
    """Run a gh CLI command and return stdout."""
    result = subprocess.run(
        ["gh", *args], capture_output=True, text=True, timeout=30
    )
    return result.stdout.strip()


def check_github_status(name: str) -> str:
    """Check the most recent workflow run status. Returns 'success', 'failure', or 'in_progress'."""
    raw = gh(
        "run", "list",
        "--workflow", f"update-{name}.yml",
        "--limit", "1",
        "--json", "status,conclusion",
    )
    if not raw:
        return "failure"  # no runs found
    runs = json.loads(raw)
    if not runs:
        return "failure"
    run = runs[0]
    if run["status"] != "completed":
        return "in_progress"
    return run.get("conclusion", "failure")


def get_run_date_and_rows(name: str) -> tuple[str | None, int | None]:
    """Get the date and row count from the latest successful workflow run."""
    raw = gh(
        "run", "list",
        "--workflow", f"update-{name}.yml",
        "--limit", "1",
        "--json", "createdAt,conclusion,databaseId",
    )
    if not raw:
        return None, None
    runs = json.loads(raw)
    if not runs or runs[0].get("conclusion") != "success":
        return None, None

    run = runs[0]
    run_date = run["createdAt"][:10]
    run_id = run["databaseId"]

    # Extract row count from the run logs
    try:
        log = subprocess.run(
            ["gh", "run", "view", str(run_id), "--log"],
            capture_output=True, text=True, timeout=60,
        ).stdout
        # Look for the rows= output line from push-status.sh
        for line in log.splitlines():
            m = re.search(r"--rows\s+(\d+)", line)
            if m:
                return run_date, int(m.group(1))
    except (subprocess.TimeoutExpired, subprocess.SubprocessError):
        pass

    return run_date, None


def fix_stale_status(name: str, dry_run: bool = False) -> bool:
    """Fix status.json for a dataset whose run succeeded but status push failed."""
    run_date, rows = get_run_date_and_rows(name)
    if not run_date:
        return False

    if dry_run:
        print(f"  [dry-run] Would update status.json: {name} = {run_date} ({rows} rows)")
        return True

    # Update status.json directly
    args = ["python", str(ROOT / "scripts" / "update-status.py"), name]
    if rows is not None:
        args.extend(["--rows", str(rows)])
    # Temporarily override the date by setting it in status.json
    data = json.loads(STATUS_FILE.read_text())
    data[name] = run_date
    if rows is not None:
        if "_rows" not in data:
            data["_rows"] = {}
        data["_rows"][name] = rows
    STATUS_FILE.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    print(f"  Fixed status.json: {name} = {run_date} ({rows} rows)")
    return True


def retry_workflow(name: str, dry_run: bool = False) -> bool:
    """Trigger a workflow_dispatch for the dataset. Returns True on success."""
    workflow = f"update-{name}.yml"
    if dry_run:
        print(f"  [dry-run] Would trigger {workflow}")
        return True
    try:
        subprocess.run(
            ["gh", "workflow", "run", workflow],
            capture_output=True, text=True, check=True, timeout=30,
        )
        print(f"  Triggered {workflow}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"  Failed to trigger {workflow}: {e.stderr.strip()}")
        return False


def create_issue(name: str, last_update: str, period_days: int, dry_run: bool = False) -> None:
    """Create a GitHub issue for a persistently failing dataset (idempotent)."""
    title = f"[watchdog] {name} pipeline failing"

    # Check for existing open issue
    existing = gh(
        "issue", "list",
        "--search", f"in:title [watchdog] {name} pipeline failing",
        "--state", "open",
        "--json", "number",
    )
    if existing:
        issues = json.loads(existing)
        if issues:
            print(f"  Issue already open: #{issues[0]['number']}")
            return

    schedule_label = {1: "daily", 7: "weekly", 31: "monthly"}.get(
        period_days, f"every {period_days} days"
    )
    body = (
        f"Dataset **{name}** has failed {MAX_RETRIES} consecutive watchdog retries.\n\n"
        f"- **Last successful update:** {last_update or 'never'}\n"
        f"- **Expected schedule:** {schedule_label}\n"
        f"- **Workflow:** `update-{name}.yml`\n\n"
        f"Please investigate manually.\n\n"
        f"_Created by the [watchdog workflow](../actions/workflows/watchdog.yml)._"
    )

    if dry_run:
        print(f"  [dry-run] Would create issue: {title}")
        return

    gh("issue", "create", "--title", title, "--body", body, "--label", "watchdog")
    print(f"  Created issue: {title}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Watchdog for dataset pipelines")
    parser.add_argument("--dry-run", action="store_true", help="Print actions without executing")
    args = parser.parse_args()

    schedules = load_workflow_schedules()
    status = load_status()
    retry_state = load_retry_state()
    today_str = date.today().isoformat()

    stale = find_stale(schedules, status)
    print(f"Checking {len(schedules)} workflows, {len(stale)} stale datasets found")

    actions: list[dict] = []

    for name in stale:
        period = schedules[name]
        last_update = status.get(name, "never")
        print(f"\n{name} (last: {last_update}, expected every {period}d)")

        # Check GitHub run status
        gh_status = check_github_status(name)
        print(f"  GitHub status: {gh_status}")

        if gh_status == "success":
            print(f"  Last run succeeded — status.json is stale, fixing")
            fixed = fix_stale_status(name, dry_run=args.dry_run)
            action_str = "status fixed" if fixed else "fix failed"
            actions.append({"dataset": name, "last_update": last_update, "period": period,
                            "status": "stale (push failed)", "action": action_str})
            continue

        if gh_status == "in_progress":
            print(f"  Run in progress, skipping")
            actions.append({"dataset": name, "last_update": last_update, "period": period,
                            "status": "in_progress", "action": "skipped"})
            continue

        # Failed — check retry state
        entry = retry_state.get(name, {"retries": 0, "first_failure": today_str})

        if name in NO_RETRY:
            print(f"  In NO_RETRY set — creating issue directly")
            create_issue(name, last_update, period, dry_run=args.dry_run)
            actions.append({"dataset": name, "last_update": last_update, "period": period,
                            "status": "failed", "action": "issue created (no-retry)"})
            continue

        if entry["retries"] < MAX_RETRIES:
            entry["retries"] += 1
            entry["last_retry"] = today_str
            if "first_failure" not in entry:
                entry["first_failure"] = today_str
            retry_state[name] = entry

            success = retry_workflow(name, dry_run=args.dry_run)
            action_str = f"retried ({entry['retries']}/{MAX_RETRIES})"
            if not success:
                action_str += " (trigger failed)"
            actions.append({"dataset": name, "last_update": last_update, "period": period,
                            "status": "failed", "action": action_str})
        else:
            create_issue(name, last_update, period, dry_run=args.dry_run)
            actions.append({"dataset": name, "last_update": last_update, "period": period,
                            "status": "failed", "action": "issue created"})

    # Clean up recovered datasets
    recovered = [n for n in list(retry_state) if n not in stale]
    for name in recovered:
        print(f"\n{name}: recovered, clearing retry state")
        del retry_state[name]

    # Save retry state (skip in dry-run mode)
    if not args.dry_run:
        save_retry_state(retry_state)

    # Write summary
    write_summary(actions, schedules, status)

    print(f"\nDone. {len(actions)} stale, {len(recovered)} recovered.")


def write_summary(actions: list[dict], schedules: dict, status: dict) -> None:
    """Write a markdown summary table to $GITHUB_STEP_SUMMARY and stdout."""
    lines = [
        "## Watchdog Summary",
        "",
        f"**Date:** {date.today().isoformat()}  ",
        f"**Workflows checked:** {len(schedules)}  ",
        f"**Stale datasets:** {len(actions)}",
        "",
        "| Dataset | Last Updated | Schedule | Action |",
        "|---------|-------------|----------|--------|",
    ]
    for a in sorted(actions, key=lambda x: x["dataset"]):
        sched = {1: "daily", 7: "weekly", 31: "monthly"}.get(
            a["period"], f"{a['period']}d"
        )
        lines.append(f"| {a['dataset']} | {a['last_update']} | {sched} | {a['action']} |")

    summary = "\n".join(lines) + "\n"
    print("\n" + summary)

    # Write to GitHub Actions step summary if available
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a") as f:
            f.write(summary)


if __name__ == "__main__":
    main()
