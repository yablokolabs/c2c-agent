"""Re-render every recorded run's JSONL as judge-readable Markdown."""

from pathlib import Path

from c2c.trajectory import render_markdown


def main() -> int:
    runs = sorted(Path("trajectories/runs").glob("*/events.jsonl"))
    if not runs:
        print("no recorded runs under trajectories/runs/")
        return 0
    import json

    for events_path in runs:
        events = [json.loads(l) for l in events_path.read_text().splitlines() if l]
        out = events_path.parent / "trajectory.md"
        out.write_text(render_markdown(events, events_path.parent.name))
        print(f"  {out}  ({len(events)} events)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
