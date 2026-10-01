"""Compare generated catalog outputs and report a validated weekly update."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
from pathlib import Path


GENERATED_FILES = (
    "data/source/song-info.json",
    "data/source/artists-info.json",
    "data/source/series-info.json",
    "data/source/.snapshot.json",
    "data/analysis-manifest.json",
    "data/catalog.json",
    "data/source-review.md",
)
MARKER = "data/source/.snapshot.json"


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def capture(root):
    """Hash the publication allowlist, ignoring only collection wall-clock times."""
    paths = set(GENERATED_FILES)
    paths.update(path.relative_to(root).as_posix() for path in (root / "data/raw").glob("*.json"))
    hashes = {}
    for name in sorted(paths):
        path = root / name
        body = path.read_bytes()
        if name == MARKER:
            marker = read_json(path)
            marker.pop("collection", None)
            body = json.dumps(marker, sort_keys=True, ensure_ascii=False).encode("utf-8")
        hashes[name] = hashlib.sha256(body).hexdigest()
    return {"hashes": hashes, "catalog": read_json(root / "data/catalog.json"),
            "manifest": read_json(root / "data/analysis-manifest.json")}


def song_label(song):
    title = song["titles"].get("en") or song["titles"].get("ja") or song["id"]
    return f"{title} ({song['id']})".replace("\n", " ").replace("\r", " ")


def render_commit_message(before, after):
    previous = {song["id"]: song for song in before["catalog"]["songs"]}
    current = {song["id"]: song for song in after["catalog"]["songs"]}
    lines = ["Refresh song catalog", ""]
    analysis_fields = {"status", "durationSeconds", "error", "occurrenceCount", "occurrences"}
    for song_id, song in current.items():
        state = after["manifest"]["songs"][song_id]
        if song_id not in previous:
            lines.append(f"- Added {song_label(song)}: {state['status']}")
            continue
        old_song = previous[song_id]
        old_state = before["manifest"]["songs"][song_id]
        changes = []
        if ({key: value for key, value in old_song.items() if key not in analysis_fields}
                != {key: value for key, value in song.items() if key not in analysis_fields}):
            changes.append("metadata updated")
        if old_state["status"] != state["status"]:
            changes.append(f"{old_state['status']} → {state['status']}")
        raw_path = f"data/raw/{song_id}.json"
        if (old_state != state
                or before["hashes"].get(raw_path) != after["hashes"].get(raw_path)
                or any(old_song.get(key) != song.get(key) for key in analysis_fields - {"status"})):
            changes.append("analysis updated")
        if changes:
            lines.append(f"- Updated {song_label(song)}: {', '.join(changes)}")
    for song_id, song in previous.items():
        if song_id not in current:
            lines.append(f"- Removed {song_label(song)}")
    if len(lines) == 2:
        lines.append("No song changes.")
    lines.extend(["", "Still missing:"])
    gaps = []
    for song_id, song in current.items():
        state = after["manifest"]["songs"][song_id]
        if state["status"] in ("failed", "unavailable"):
            reason = state.get("error") or (
                "No verified recording" if state["status"] == "unavailable" else "Analysis failed")
            reason = reason.replace("\n", " ").replace("\r", " ")
            gaps.append(f"- {song_label(song)}: {state['status']} — {reason}")
    lines.extend(gaps or ["None."])
    return "\n".join(lines) + "\n"


def cell(value):
    return html.escape(str(value)).replace("|", "&#124;").replace("\n", " ").replace("\r", " ")


def render_report(before, after, manifest, pattern_hash, override_hash, run_url):
    changed = before["hashes"] != after["hashes"]
    catalog = after["catalog"]
    lines = [
        "# Weekly catalog update", "",
        "Validated catalog changes are ready to commit to main."
        if changed else "No substantive generated-data changes; no commit is needed.",
        "", f"[Workflow run]({run_url})", "",
        "Lint, Python tests, frontend tests, data validation, type-checking, and the production build passed.",
        "", "| Metric | Before | After |", "| --- | ---: | ---: |",
    ]
    for key, value in catalog["metrics"].items():
        lines.append(f"| {cell(key)} | {before['catalog']['metrics'].get(key, 0)} | {value} |")
    lines.extend(["", "## Song changes", ""])
    changes = render_commit_message(before, after).split("\n\nStill missing:", 1)[0].splitlines()[2:]
    lines.extend(cell(line) for line in changes)
    lines.extend(["", "## Failed and unavailable recordings", "",
                  "| ID | Title | Status | Reason |", "| --- | --- | --- | --- |"])
    gaps = 0
    for song in catalog["songs"]:
        state = manifest["songs"][song["id"]]
        if state["status"] not in ("failed", "unavailable"):
            continue
        gaps += 1
        title = song["titles"].get("en") or song["titles"].get("ja") or song["id"]
        reason = state.get("error") or "No verified recording; see data/source-review.md."
        lines.append(f"| {cell(song['id'])} | {cell(title)} | {cell(state['status'])} | {cell(reason)} |")
    if not gaps:
        lines.append("| — | None | — | — |")
    analysis = manifest["analysis"]
    lines.extend(["", "## Provenance", "",
                  f"- Source snapshot: `{manifest['sourceSnapshot']}`",
                  f"- Detector revision: `{analysis['revision']}`",
                  f"- Detector configuration: `{analysis['configVersion']}`",
                  f"- Patterns SHA-256: `{pattern_hash}`",
                  f"- Overrides SHA-256: `{override_hash}`", "",
                  "Unresolved source verification details are recorded in `data/source-review.md`.", ""])
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("capture", "report"))
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--commit-message", type=Path)
    parser.add_argument("--run-url")
    args = parser.parse_args(argv)
    if args.command == "report" and (args.commit_message is None or not args.run_url):
        parser.error("report requires --commit-message and --run-url")
    current = capture(args.root)
    if args.command == "capture":
        args.baseline.write_text(json.dumps(current, ensure_ascii=False), encoding="utf-8")
        return 0
    baseline = read_json(args.baseline)
    changed = baseline["hashes"] != current["hashes"]
    hashes = [hashlib.sha256((args.root / name).read_bytes()).hexdigest()
              for name in ("data/patterns.json", "data/overrides.json")]
    report = render_report(baseline, current, read_json(args.root / "data/analysis-manifest.json"),
                           *hashes, args.run_url)
    args.commit_message.write_text(render_commit_message(baseline, current), encoding="utf-8")
    for variable, content in (("GITHUB_OUTPUT", f"changed={str(changed).lower()}\n"),
                              ("GITHUB_STEP_SUMMARY", report)):
        if os.environ.get(variable):
            with Path(os.environ[variable]).open("a", encoding="utf-8") as handle:
                handle.write(content)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
