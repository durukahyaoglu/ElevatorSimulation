import csv
import statistics
from pathlib import Path
from fpdf import FPDF

from building import Building
from models import Request, PassengerJourney


BASE_DIR    = Path(__file__).parent
INPUT_DIR   = BASE_DIR / "inputs"
OUTPUT_DIR = BASE_DIR / "outputs"

TOTAL_TICKS = 100

# Each scenario defines a name (matching its input CSV filename),
# a description of the edge case being tested, and building config.
SCENARIOS = [
    {
        "name": "baseline",
        "description": "Standard case — 2 elevators, staggered arrivals",
        "num_elevators": 2,
        "num_floors": 60,
        "max_capacity": 10,
    },
    {
        "name": "scenario_single_elevator",
        "description": "Edge case — only 1 elevator serving 6 passengers",
        "num_elevators": 1,
        "num_floors": 60,
        "max_capacity": 5,
    },
    {
        "name": "scenario_many_elevators",
        "description": "Edge case — 8 elevators for only 3 passengers (under-utilised)",
        "num_elevators": 8,
        "num_floors": 60,
        "max_capacity": 10,
    },
    {
        "name": "scenario_capacity_overflow",
        "description": "Edge case — 8 passengers arrive at t=0, elevators hold only 2 each",
        "num_elevators": 2,
        "num_floors": 60,
        "max_capacity": 2,
    },
    {
        "name": "scenario_simultaneous_same_floor",
        "description": "Edge case — 6 passengers all on floor 1 going to different floors",
        "num_elevators": 2,
        "num_floors": 20,
        "max_capacity": 5,
    },
    {
        "name": "scenario_bidirectional",
        "description": "Edge case — simultaneous up and down traffic across 3 elevators",
        "num_elevators": 3,
        "num_floors": 30,
        "max_capacity": 4,
    },
    {
        "name": "scenario_express_elevator",
        "description": "Bonus — 1 express elevator serving floors {1,20,40,60} only",
        "num_elevators": 3,
        "num_floors": 60,
        "max_capacity": 5,
        "express_floors": {1, 20, 40, 60},
    },
]


def parse_requests(path: Path) -> list[Request]:
    """Parse a CSV file with columns time, id, source, dest into a list of Requests."""
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        return [
            Request(
                time=int(row["time"]),
                id=row["id"],
                source=int(row["source"]),
                destination=int(row["dest"]),
            )
            for row in reader
        ]


def write_elevator_log(log: list[dict], path: Path):
    """Write per-tick elevator positions to a CSV file."""
    if not log:
        return
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=log[0].keys())
        writer.writeheader()
        writer.writerows(log)


def format_stats(
    journeys: list[PassengerJourney],
    waiting: list[PassengerJourney],
    description: str,
    elevators: list,
) -> str:
    """Build the stats report as a string."""
    completed = [j for j in journeys if j.alight_tick is not None]
    unserved  = [j for j in journeys if j.alight_tick is None]

    lines = []
    lines.append("=" * 52)
    lines.append(f"  {description}")
    lines.append("=" * 52)
    lines.append(f"  Total requests : {len(journeys)}")
    lines.append(f"  Completed      : {len(completed)}")
    lines.append(f"  Still waiting  : {len(waiting)}")
    lines.append(f"  In transit     : {len(unserved) - len(waiting)}")

    if not completed:
        lines.append("  (no completed journeys to report)")
    else:
        def summary(values: list[int], label: str):
            lines.append(f"\n  {label}")
            lines.append(f"    Min : {min(values)} ticks")
            lines.append(f"    Max : {max(values)} ticks")
            lines.append(f"    Avg : {statistics.mean(values):.1f} ticks")
            if len(values) > 1:
                lines.append(f"    Std : {statistics.stdev(values):.1f} ticks")

        summary([j.wait_time   for j in completed], "Wait time   (request → board)")
        summary([j.travel_time for j in completed], "Travel time (board → alight)")
        summary([j.total_time  for j in completed], "Total time  (request → alight)")

        lines.append("\n  Notable observations:")
        slowest_wait  = max(completed, key=lambda j: j.wait_time)
        slowest_total = max(completed, key=lambda j: j.total_time)
        fastest_total = min(completed, key=lambda j: j.total_time)
        lines.append(f"    Longest wait  : {slowest_wait.id} waited {slowest_wait.wait_time} ticks at floor {slowest_wait.origin}")
        lines.append(f"    Longest trip  : {slowest_total.id} took {slowest_total.total_time} ticks total")
        lines.append(f"    Shortest trip : {fastest_total.id} took {fastest_total.total_time} ticks total")
        if unserved:
            ids = ", ".join(j.id for j in unserved)
            lines.append(f"    Unfinished    : {ids} did not complete journey within {TOTAL_TICKS} ticks")

    # Elevator usage breakdown
    lines.append(f"\n  Elevator usage:")
    passengers_per_elevator = {e.id: [] for e in elevators}
    for j in journeys:
        if j.elevator_id is not None:
            passengers_per_elevator[j.elevator_id].append(j.id)

    for e in elevators:
        served   = len(passengers_per_elevator[e.id])
        traveled = e.floors_traveled
        util_pct = traveled / (TOTAL_TICKS + 1) * 100
        label    = f"E{e.id}" + (" [EXPRESS floors=" + str(sorted(e.allowed_floors)) + "]" if e.is_express else "")
        if served == 0:
            lines.append(f"    {label} : never assigned a passenger")
        else:
            pax = ", ".join(passengers_per_elevator[e.id])
            lines.append(f"    {label} : {served} passenger(s) [{pax}]  |  {traveled} floors traveled  |  {util_pct:.0f}% utilization")

    lines.append("=" * 52)
    return "\n".join(lines)


def extract_metrics(journeys: list[PassengerJourney], elevators: list) -> dict:
    """Extract key metrics from a completed simulation for comparison purposes."""
    completed = [j for j in journeys if j.alight_tick is not None]
    return {
        "completed":  len(completed),
        "total":      len(journeys),
        "avg_wait":   statistics.mean([j.wait_time   for j in completed]) if completed else None,
        "max_wait":   max([j.wait_time   for j in completed]) if completed else None,
        "avg_total":  statistics.mean([j.total_time  for j in completed]) if completed else None,
        "max_total":  max([j.total_time  for j in completed]) if completed else None,
        "utils":      [f"E{e.id}: {e.floors_traveled / (TOTAL_TICKS + 1) * 100:.0f}%"
                       for e in elevators if e.floors_traveled > 0],
    }


SCHEDULER_LABELS = {
    "nearest_car": "Nearest Car",
    "round_robin": "Round Robin",
    "zone_based":  "Zone Based",
}


def fmt(val) -> str:
    """Format a metric value for display."""
    return f"{val:.1f}" if isinstance(val, float) else (str(val) if val is not None else "-")


def comparison_rows(results: dict) -> list[tuple]:
    """Return (metric, *per-scheduler values) rows; column order follows results.keys()."""
    getters = [
        ("Completed",      lambda r: f"{r['completed']}/{r['total']}"),
        ("Avg wait time",  lambda r: f"{fmt(r['avg_wait'])} ticks"),
        ("Max wait time",  lambda r: f"{fmt(r['max_wait'])} ticks"),
        ("Avg total time", lambda r: f"{fmt(r['avg_total'])} ticks"),
        ("Max total time", lambda r: f"{fmt(r['max_total'])} ticks"),
        ("Utilization",    lambda r: ", ".join(r["utils"])),
    ]
    return [(label,) + tuple(fn(results[s]) for s in results) for label, fn in getters]


def print_comparison(scenario_name: str, results: dict):
    """Print a side-by-side scheduler comparison table to the console."""
    headers = [SCHEDULER_LABELS.get(s, s) for s in results]
    w = 16
    total_w = 22 + (w + 1) * len(headers)
    print(f"\n  {'─' * total_w}")
    print(f"  COMPARISON: {scenario_name}")
    print(f"  {'─' * total_w}")
    header_line = f"  {'Metric':<22}" + "".join(f" {h:>{w}}" for h in headers)
    print(header_line)
    print(f"  {'─' * total_w}")
    for row in comparison_rows(results):
        metric, *vals = row
        print(f"  {metric:<22}" + "".join(f" {v:>{w}}" for v in vals))
    print(f"  {'─' * total_w}")


def _ascii(text: str) -> str:
    """Replace non-latin-1 characters so fpdf core fonts can render the text."""
    return text.replace("—", "-").replace("–", "-").replace("’", "'")


def write_comparison_pdf(all_results: list[dict], path: Path):
    """Write a PDF report comparing all schedulers across all scenarios."""
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    # Title
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, "Elevator Simulation - Scheduler Comparison", align="C")
    pdf.ln(4)
    pdf.set_font("Helvetica", "I", 10)
    pdf.set_text_color(100, 100, 100)
    pdf.cell(0, 6, "Nearest Car vs Round Robin vs Zone Based across all scenarios", align="C")
    pdf.set_text_color(0, 0, 0)
    pdf.ln(10)

    row_h = 7
    hdr_h = 8

    for entry in all_results:
        scenario = entry["scenario"]
        results  = entry["results"]     # dict: scheduler_name -> metrics dict
        n_sched  = len(results)

        # Dynamic column widths: metric col + equal share for each scheduler
        page_w   = pdf.w - pdf.l_margin - pdf.r_margin
        metric_w = 55.0
        sched_w  = (page_w - metric_w) / n_sched

        # Scenario heading
        pdf.set_font("Helvetica", "B", 11)
        pdf.set_fill_color(30, 30, 30)
        pdf.set_text_color(255, 255, 255)
        pdf.cell(0, hdr_h, _ascii(f"  {scenario['name']}  -  {scenario['description']}"), fill=True)
        pdf.ln(hdr_h)
        pdf.set_text_color(0, 0, 0)

        # Config line
        pdf.set_font("Helvetica", "I", 9)
        pdf.set_text_color(80, 80, 80)
        pdf.cell(0, 5, f"  Elevators: {scenario['num_elevators']}   Floors: {scenario['num_floors']}   Capacity/elevator: {scenario['max_capacity']}")
        pdf.ln(6)
        pdf.set_text_color(0, 0, 0)

        # Table header row
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_fill_color(220, 220, 220)
        pdf.cell(metric_w, row_h, "Metric", border=1, fill=True, align="C")
        for sched in results:
            pdf.cell(sched_w, row_h, SCHEDULER_LABELS.get(sched, sched), border=1, fill=True, align="C")
        pdf.ln(row_h)

        # Table data rows — alternate shading
        pdf.set_font("Helvetica", "", 9)
        for i, row in enumerate(comparison_rows(results)):
            metric, *vals = row
            fill = i % 2 == 0
            pdf.set_fill_color(245, 245, 245) if fill else pdf.set_fill_color(255, 255, 255)
            pdf.cell(metric_w, row_h, f"  {metric}", border=1, fill=fill)
            for v in vals:
                # Long utilization strings need smaller font to fit the cell
                if len(v) > 18:
                    pdf.set_font("Helvetica", "", 7)
                pdf.cell(sched_w, row_h, v, border=1, fill=fill, align="C")
                pdf.set_font("Helvetica", "", 9)
            pdf.ln(row_h)

        pdf.ln(6)

    pdf.output(str(path))
    print(f"\nComparison PDF written to {path.name}")


def run_simulation(requests: list[Request], building: Building) -> list[dict]:
    """Run the simulation and return the per-tick elevator position log."""
    queue = sorted(requests, key=lambda r: r.time)
    log: list[dict] = []

    for tick in range(TOTAL_TICKS + 1):
        due = []
        while queue and queue[0].time <= tick:
            due.append(queue.pop(0))

        for r in due:
            assigned = building.request(
                origin=r.source, destination=r.destination,
                passenger_id=r.id, tick=tick,
            )
            status = f"assigned Elevator {assigned}" if assigned is not None else "QUEUED (all elevators full, will retry)"
            print(f"    [Tick {tick:>3}] {r.id}: floor {r.source} → {r.destination}  →  {status}")

        row = {"tick": tick}
        for e in building.elevators:
            row[f"E{e.id}_floor"]     = e.current_floor
            row[f"E{e.id}_direction"] = e.direction.value
        log.append(row)

        building.step(tick)

    return log


def run_scenario_with_scheduler(scenario: dict, scheduler: str, requests: list[Request]) -> tuple:
    """Run one scenario with the given scheduler, return (log, building)."""
    building = Building(
        num_floors=scenario["num_floors"],
        num_elevators=scenario["num_elevators"],
        max_capacity=scenario["max_capacity"],
        scheduler=scheduler,
        express_floors=scenario.get("express_floors"),
    )
    log = run_simulation(requests, building)
    return log, building


def main():
    OUTPUT_DIR.mkdir(exist_ok=True)

    schedulers  = ["nearest_car", "round_robin", "zone_based"]
    all_results = []   # collected for the PDF report

    for scenario in SCENARIOS:
        name        = scenario["name"]
        description = scenario["description"]
        input_path  = INPUT_DIR / f"{name}.csv"
        requests    = parse_requests(input_path)

        print(f"\n{'=' * 52}")
        print(f"  SCENARIO : {name}")
        print(f"  {description}")
        print(f"  Elevators: {scenario['num_elevators']}  |  Floors: {scenario['num_floors']}  |  Capacity: {scenario['max_capacity']}")
        print(f"{'=' * 52}")

        results = {}
        for scheduler in schedulers:
            print(f"\n  [{scheduler.upper().replace('_', ' ')}]")
            log, building = run_scenario_with_scheduler(scenario, scheduler, requests)

            stats = format_stats(
                building.journeys, building.waiting, description, building.elevators
            )
            log_path   = OUTPUT_DIR / f"{name}_{scheduler}_elevator_log.csv"
            stats_path = OUTPUT_DIR / f"{name}_{scheduler}_stats.txt"

            write_elevator_log(log, log_path)
            stats_path.write_text(stats)
            print(f"\n{stats}")
            print(f"\n    Elevator log → {log_path.name}")
            print(f"    Stats        → {stats_path.name}")

            results[scheduler] = extract_metrics(building.journeys, building.elevators)

        print_comparison(name, results)
        all_results.append({"scenario": scenario, "results": results})

    pdf_path = OUTPUT_DIR / "comparison_report.pdf"
    write_comparison_pdf(all_results, pdf_path)


if __name__ == "__main__":
    main()
