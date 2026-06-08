# Elevator Simulation

A discrete-time simulation of an intelligent **Destination Dispatch** elevator system written in Python. Passengers specify both their origin and destination floor at the time of request, and the scheduler immediately assigns the optimal elevator to minimise total journey time.

---

## How to Run

### Prerequisites
- Python 3.12+
- pip

### Setup

```bash
# Clone the repository
git clone https://github.com/durukahyaoglu/ElevatorSimulation.git
cd ElevatorSimulation

# Create and activate a virtual environment
python3.12 -m venv venv
source venv/bin/activate      # macOS / Linux
venv\Scripts\activate         # Windows

# Install dependencies
pip install -r requirements.txt
```

### Running the simulation

```bash
python main.py
```

This runs all scenarios defined in `main.py` and writes results to the `outputs/` folder.

### Adding a new scenario

1. Create a CSV file in `inputs/` with the format:
   ```
   time,id,source,dest
   0,passenger1,1,10
   5,passenger2,8,2
   ```

2. Add an entry to the `SCENARIOS` list in `main.py`:
   ```python
   {
       "name": "my_scenario",        # must match the CSV filename
       "description": "My test",
       "num_elevators": 3,
       "num_floors": 20,
       "max_capacity": 5,
   }
   ```

3. Re-run `python main.py`.

### Output files

| File | Description |
|---|---|
| `outputs/<scenario>_elevator_log.csv` | Elevator floor and direction at every tick |
| `outputs/<scenario>_stats.txt` | Min / max / avg wait and total times with observations |

---

## Project Structure

```
ElevatorSimulation/
├── elevator.py       # Elevator class — movement, boarding, SCAN logic
├── building.py       # Building class — assignment, cost function, waiting queue
├── models.py         # Request and PassengerJourney dataclasses
├── main.py           # Simulation runner, scenarios, output writers
├── inputs/           # Input CSV files (one per scenario)
├── outputs/          # Generated logs and stats (one pair per scenario)
├── tests/
│   └── test_elevator.py
└── requirements.txt
```

---

## Time Spent

~ 10 hours

---

## Assumptions and Simplifications

- **One time unit = one floor of travel.** Boarding and alighting are treated as instantaneous (zero time cost). In a real system, door open/close time would add at least one tick per stop.

- **Greedy assignment at request time.** Each request is assigned to the best available elevator the moment it arrives. There is no look-ahead or re-optimisation after assignment — once a passenger is assigned to an elevator, that assignment is final.

- **SCAN movement within an elevator.** Once assigned, an elevator sweeps in one direction through all queued stops before reversing. This is efficient for grouped traffic but can cause head-of-line delay for passengers whose stop is behind the current sweep direction.

- **Waiting queue is FIFO.** When all elevators are at capacity, passengers queue in arrival order. A more sophisticated system might re-rank waiting passengers dynamically as elevator states change.

- **No door-hold or real-time rebooking.** A passenger cannot change their destination after assignment, matching the Destination Dispatch model in the spec.

- **Finite simulation window (100 ticks).** The simulation runs for exactly `TOTAL_TICKS = 100` ticks. Any passenger whose journey cannot physically complete within that window — for example, a late-arriving request to a distant floor — will appear as "unfinished" in the stats. This is a reporting artefact of the time limit, not a scheduler failure. In a production system the simulation would run indefinitely.

---

## Trade-offs

| Decision | Alternative | Reason chosen |
|---|---|---|
| Nearest Car (assignment) + SCAN (movement) | Pure SCAN or Round Robin | Nearest Car minimises `wait + travel` per passenger; SCAN keeps movement efficient once assigned |
| Greedy single-step assignment | Batch optimisation | Greedy is O(n·e) per request and satisfies the real-time constraint; batch optimisation would require knowing future requests |
| Instantaneous boarding | Boarding costs one tick | The spec defines one time unit as one floor of travel only; boarding time is unspecified |
| FIFO waiting queue | Priority queue by wait time | FIFO is fair and prevents starvation; priority by wait time would be equivalent here since all passengers arrive with the same urgency |

---

## What I Would Improve With More Time

1. **Re-assignment on new requests.** Currently, once a passenger is assigned, their elevator is locked in. A smarter system would re-evaluate existing assignments whenever a new elevator becomes idle or a new request arrives, potentially reassigning to reduce overall cost.

2. **Boarding time as a configurable cost.** Adding a `dwell_time` parameter per stop would make the simulation more realistic and affect the cost estimator accordingly.

3. **Fairness vs. efficiency trade-off.** The current cost function optimises purely for `wait + travel`. A fairness-weighted objective (e.g. cap max wait time at N ticks, then prioritise longest-waiting passenger) would prevent stragglers in high-traffic scenarios.

4. **More realistic benchmarking.** Generate large randomised request sets with realistic traffic patterns (morning peak up, evening peak down, midday random) to stress-test the scheduler at scale.

5. **Look-ahead batch scheduling.** All three algorithms here are greedy (assign at request time, no re-optimisation). A batch scheduler — e.g. solve an assignment problem every N ticks — could reduce total system cost, at the expense of increased latency to assignment.

---

## Scheduler Comparison Results

Three schedulers are compared across all scenarios. A formatted PDF report is available at `outputs/comparison_report.pdf`.

| Scheduler | Strategy |
|---|---|
| **Nearest Car** (default) | Pick the elevator with the lowest estimated `wait + travel` time using SCAN-path cost |
| **Round Robin** (bonus) | Cycle through elevators in order regardless of position |
| **Zone Based** (bonus) | Divide floors into equal zones — each elevator owns one zone and only serves passengers in it |

---

### baseline — 2 elevators, staggered arrivals

| Metric | Nearest Car | Round Robin | Zone Based |
|---|---|---|---|
| Completed | 3/3 | 3/3 | 3/3 |
| Avg wait time | 6.0 ticks | 2.7 ticks | 2.7 ticks |
| Max wait time | 18 ticks | 8 ticks | 8 ticks |
| Avg total time | 40.3 ticks | 57.7 ticks | 57.7 ticks |
| Max total time | 49 ticks | 89 ticks | 89 ticks |
| Utilization | E0: 50%, E1: 38% | E0: 99%, E1: 36% | E0: 99%, E1: 0% |

> Nearest Car wins on total time — it co-locates passenger2 with passenger1 on E0, avoiding a long round trip. Zone Based matches Round Robin but leaves E1 idle since all requests originate from floors in E0's zone.

---

### scenario_single_elevator — 1 elevator, 6 passengers

| Metric | Nearest Car | Round Robin | Zone Based |
|---|---|---|---|
| Completed | 3/6 | 3/6 | 3/6 |
| Avg wait time | 1.0 ticks | 1.0 ticks | 1.0 ticks |
| Max wait time | 3 ticks | 3 ticks | 3 ticks |
| Avg total time | 36.3 ticks | 36.3 ticks | 36.3 ticks |
| Max total time | 53 ticks | 53 ticks | 53 ticks |
| Utilization | E0: 100% | E0: 100% | E0: 100% |

> With one elevator all three schedulers are identical — the bottleneck is hardware, not scheduling.

---

### scenario_many_elevators — 8 elevators, 3 passengers

| Metric | Nearest Car | Round Robin | Zone Based |
|---|---|---|---|
| Completed | 2/3 | 3/3 | 3/3 |
| Avg wait time | 6.5 ticks | 13.7 ticks | 13.7 ticks |
| Max wait time | 13 ticks | 28 ticks | 28 ticks |
| Avg total time | 50.5 ticks | 52.7 ticks | 52.7 ticks |
| Max total time | 58 ticks | 58 ticks | 58 ticks |
| Utilization | E0: 100%, rest 0% | E0/E1/E2 used | E0/E1/E3 used |

> Nearest Car saturates E0 (all requests go to the closest elevator) and misses one passenger within the window. Round Robin and Zone Based spread load across multiple elevators and complete all 3 journeys.

---

### scenario_capacity_overflow — 2 elevators, cap 2, 8 passengers

| Metric | Nearest Car | Round Robin | Zone Based |
|---|---|---|---|
| Completed | 5/8 | 4/8 | 2/8 |
| Avg wait time | 11.2 ticks | 0 ticks | 0 ticks |
| Max wait time | 56 ticks | 0 ticks | 0 ticks |
| Avg total time | 46.2 ticks | 33.0 ticks | 43.0 ticks |
| Max total time | 99 ticks | 48 ticks | 48 ticks |
| Utilization | E0: 100%, E1: 100% | E0: 100%, E1: 100% | E0: 100%, E1: 0% |

> Nearest Car wins on completions (5/8) by retrying the waiting queue with the best-fit elevator. Zone Based is worst here — all requests fall in E0's zone so E1 is never used and most passengers time out.

---

### scenario_simultaneous_same_floor — 6 passengers all on floor 1

| Metric | Nearest Car | Round Robin | Zone Based |
|---|---|---|---|
| Completed | 6/6 | 6/6 | 6/6 |
| Avg wait time | 0 ticks | 0 ticks | 6.2 ticks |
| Max wait time | 0 ticks | 0 ticks | 37 ticks |
| Avg total time | 9.7 ticks | 9.7 ticks | 16.0 ticks |
| Max total time | 18 ticks | 18 ticks | 48 ticks |
| Utilization | E0: 19%, E1: 11% | E0: 14%, E1: 19% | E0: 49%, E1: 0% |

> Zone Based penalises passengers heavily — all originate from floor 1 (E0's zone) so E1 is never assigned, wait times spike to 37 ticks. Nearest Car and Round Robin both deliver 0 wait time.

---

### scenario_bidirectional — 3 elevators, mixed up/down traffic

| Metric | Nearest Car | Round Robin | Zone Based |
|---|---|---|---|
| Completed | 8/8 | 8/8 | 8/8 |
| Avg wait time | 10.4 ticks | 10.4 ticks | 10.4 ticks |
| Max wait time | 28 ticks | 28 ticks | 28 ticks |
| Avg total time | 37.4 ticks | 34.6 ticks | 33.4 ticks |
| Max total time | 57 ticks | 57 ticks | 57 ticks |
| Utilization | E0: 57%, E1: 51%, E2: 0% | E0: 57%, E1: 48%, E2: 29% | E0: 29%, E1: 36%, E2: 57% |

> Zone Based wins on avg total time — origin floors are naturally spread across zones so each elevator handles nearby traffic with minimal detour. Nearest Car never assigns E2 because E0/E1 always appear closer.
