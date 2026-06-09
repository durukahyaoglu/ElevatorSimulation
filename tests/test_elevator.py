import sys
import os

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from elevator import Elevator, Direction
from building import Building
from models import Request


# Helpers to keep tests concise with the updated signatures
def req(b: Building, origin: int, destination: int, pid: str = "p", tick: int = 0):
    return b.request(origin=origin, destination=destination, passenger_id=pid, tick=tick)

def step(b: Building, tick: int = 0):
    b.step(tick)


class TestElevator:
    def test_initial_state(self):
        e = Elevator(0, 10, max_capacity=5)
        assert e.current_floor == 1
        assert e.direction == Direction.IDLE
        assert e.is_idle()
        assert e.current_passengers == 0

    def test_moves_up_toward_destination(self):
        e = Elevator(0, 10, max_capacity=5)
        e.assign_passenger(origin=1, destination=3)
        e.step(tick=0)
        assert e.current_floor == 2
        assert e.direction == Direction.UP

    def test_moves_down_toward_destination(self):
        e = Elevator(0, 10, max_capacity=5)
        e.current_floor = 5
        e.assign_passenger(origin=5, destination=2)
        e.step(tick=0)
        assert e.current_floor == 4
        assert e.direction == Direction.DOWN

    def test_stops_at_destination(self):
        e = Elevator(0, 10, max_capacity=5)
        e.current_floor = 4
        e.assign_passenger(origin=4, destination=5)
        e.step(tick=0)
        assert e.current_floor == 5
        assert e.is_idle()

    def test_ignores_out_of_range_floor(self):
        e = Elevator(0, 10, max_capacity=5)
        e.assign_passenger(origin=0, destination=11)
        assert not e.destinations

    def test_passengers_board_at_origin(self):
        e = Elevator(0, 10, max_capacity=5)
        e.assign_passenger(origin=1, destination=5)
        e.step(tick=0)  # services floor 1 (origin), boards passenger, then moves to 2
        assert e.current_passengers == 1

    def test_passengers_alight_at_destination(self):
        e = Elevator(0, 10, max_capacity=5)
        e.current_floor = 4
        e.assign_passenger(origin=4, destination=5)
        e.step(tick=0)  # boards at 4, moves to 5, alights at 5
        assert e.current_passengers == 0
        assert e.is_idle()

    def test_board_and_alight_ticks_recorded(self):
        from models import PassengerJourney
        e = Elevator(0, 10, max_capacity=5)
        j = PassengerJourney(id="p1", request_tick=0, origin=1, destination=3)
        e.assign_passenger(origin=1, destination=3, journey=j)
        e.step(tick=5)   # boards at floor 1 on tick 5, moves to floor 2
        assert j.board_tick == 5
        e.step(tick=6)   # moves to floor 3, alights
        assert j.alight_tick == 6
        assert j.wait_time == 5
        assert j.travel_time == 1
        assert j.total_time == 6


class TestCapacity:
    def test_has_capacity_when_empty(self):
        e = Elevator(0, 10, max_capacity=2)
        assert e.has_capacity()

    def test_no_capacity_when_full(self):
        e = Elevator(0, 10, max_capacity=2)
        e.assign_passenger(origin=1, destination=5)
        e.assign_passenger(origin=2, destination=6)
        assert not e.has_capacity()

    def test_pending_pickups_count_against_capacity(self):
        e = Elevator(0, 10, max_capacity=1)
        e.assign_passenger(origin=3, destination=7)
        assert not e.has_capacity()  # 0 boarded + 1 pending pickup = at capacity


class TestEstimateTime:
    def test_idle_elevator_direct_distance(self):
        e = Elevator(0, 20, max_capacity=5)
        e.current_floor = 5
        assert e.estimate_time_to_floor(10) == 5
        assert e.estimate_time_to_floor(2) == 3

    def test_going_up_target_ahead(self):
        # Elevator at 3 going up with stop at 8 — target 6 is ahead, no detour
        e = Elevator(0, 20, max_capacity=5)
        e.current_floor = 3
        e.assign_passenger(origin=3, destination=8)
        e.step(tick=0)  # boards at 3, moves to 4, now going UP
        assert e.estimate_time_to_floor(6) == 6 - e.current_floor

    def test_going_up_target_behind_requires_turnaround(self):
        # Elevator at 3 going up with highest stop at 8 — target 1 is behind
        # Must go 3→8 (5 ticks) then 8→1 (7 ticks) = 12 ticks
        e = Elevator(0, 20, max_capacity=5)
        e.current_floor = 3
        e.direction = Direction.UP
        e.dropoffs = {8}
        assert e.estimate_time_to_floor(1) == (8 - 3) + (8 - 1)

    def test_going_down_target_behind_requires_turnaround(self):
        # Elevator at 8 going down with lowest stop at 2 — target 10 is behind
        # Must go 8→2 (6 ticks) then 2→10 (8 ticks) = 14 ticks
        e = Elevator(0, 20, max_capacity=5)
        e.current_floor = 8
        e.direction = Direction.DOWN
        e.dropoffs = {2}
        assert e.estimate_time_to_floor(10) == (8 - 2) + (10 - 2)

    def test_cost_is_wait_plus_travel(self):
        b = Building(num_floors=20, num_elevators=1, max_capacity=5)
        e = b.elevators[0]
        e.current_floor = 1
        # Idle elevator: wait = |1-5| = 4, travel = |5-10| = 5, total = 9
        assert b._cost(e, origin=5, destination=10) == 9

    def test_cost_prefers_elevator_on_the_way(self):
        b = Building(num_floors=20, num_elevators=2, max_capacity=5)
        # Elevator 0: at floor 3, going UP toward floor 10 — origin 5 is ahead
        e0 = b.elevators[0]
        e0.current_floor = 3
        e0.direction = Direction.UP
        e0.dropoffs = {10}
        # Elevator 1: at floor 15, idle — has to come all the way down to 5
        e1 = b.elevators[1]
        e1.current_floor = 15
        cost0 = b._cost(e0, origin=5, destination=8)
        cost1 = b._cost(e1, origin=5, destination=8)
        assert cost0 < cost1


class TestWaitingQueue:
    def test_request_queued_when_full(self):
        b = Building(num_floors=10, num_elevators=1, max_capacity=1)
        req(b, 2, 8, "p1")
        result = req(b, 3, 9, "p2")
        assert result is None
        assert any(j.origin == 3 and j.destination == 9 for j in b.waiting)

    def test_waiting_request_assigned_when_capacity_frees(self):
        b = Building(num_floors=10, num_elevators=1, max_capacity=1)
        req(b, 1, 2, "p1")  # fills elevator; boards at 1, drops at 2
        req(b, 5, 8, "p2")  # goes to waiting queue
        assert any(j.origin == 5 for j in b.waiting)
        for t in range(10):
            step(b, t)
            if not b.waiting:
                break
        assert not b.waiting  # waiting request was eventually assigned

    def test_waiting_queue_is_fifo(self):
        b = Building(num_floors=10, num_elevators=1, max_capacity=1)
        req(b, 1, 9, "p1")  # fills elevator
        req(b, 2, 7, "p2")  # queued first
        req(b, 3, 6, "p3")  # queued second
        assert [(j.origin, j.destination) for j in b.waiting] == [(2, 7), (3, 6)]


class TestDestinationDispatch:
    def test_request_returns_elevator_id(self):
        b = Building(num_floors=10, num_elevators=2, max_capacity=5)
        assigned = req(b, 3, 7)
        assert assigned in [0, 1]

    def test_request_queues_origin_and_destination(self):
        # Destination is held in _pending until the passenger boards at origin
        b = Building(num_floors=10, num_elevators=1, max_capacity=5)
        req(b, 3, 7)
        assert 3 in b.elevators[0].pickups
        j = b.elevators[0]._pending[3][0]
        assert j.destination == 7

    def test_request_rejected_when_all_full(self):
        b = Building(num_floors=10, num_elevators=1, max_capacity=1)
        req(b, 2, 8, "p1")
        result = req(b, 3, 9, "p2")
        assert result is None

    def test_two_requests_split_across_elevators(self):
        b = Building(num_floors=10, num_elevators=2, max_capacity=5)
        req(b, 2, 8, "p1")
        req(b, 9, 1, "p2")
        total_pickups = sum(len(e.pickups) for e in b.elevators)
        assert total_pickups == 2

    def test_elevator_reaches_origin_then_destination(self):
        b = Building(num_floors=10, num_elevators=1, max_capacity=5)
        req(b, 3, 6)
        for t in range(20):
            step(b, t)
        assert b.elevators[0].current_floor == 6
        assert b.elevators[0].is_idle()
        assert b.elevators[0].current_passengers == 0

    def test_journey_timestamps_recorded_end_to_end(self):
        b = Building(num_floors=10, num_elevators=1, max_capacity=5)
        req(b, origin=1, destination=4, pid="p1", tick=0)
        for t in range(10):
            step(b, t)
        j = b.journeys[0]
        assert j.board_tick is not None
        assert j.alight_tick is not None
        assert j.wait_time >= 0
        assert j.travel_time >= 0
        assert j.total_time == j.wait_time + j.travel_time


class TestExpressElevator:
    EXPRESS_FLOORS = {1, 10, 20}

    def _building(self, num_elevators=2):
        """2-elevator building where the last elevator is express (floors 1, 10, 20)."""
        return Building(
            num_floors=20, num_elevators=num_elevators,
            max_capacity=5, express_floors=self.EXPRESS_FLOORS,
        )

    def test_express_elevator_created_as_last(self):
        b = self._building()
        assert b.elevators[-1].is_express
        assert b.elevators[-1].allowed_floors == self.EXPRESS_FLOORS
        assert not b.elevators[0].is_express

    def test_can_accept_returns_true_for_allowed_floors(self):
        b = self._building()
        e = b.elevators[-1]
        assert e.can_accept(1, 20)
        assert e.can_accept(10, 1)

    def test_can_accept_returns_false_for_disallowed_floors(self):
        b = self._building()
        e = b.elevators[-1]
        assert not e.can_accept(1, 15)   # destination not in express floors
        assert not e.can_accept(5, 10)   # origin not in express floors
        assert not e.can_accept(3, 7)    # neither floor in express set

    def test_regular_elevator_always_accepts(self):
        b = self._building()
        e = b.elevators[0]
        assert e.can_accept(1, 15)
        assert e.can_accept(3, 17)

    def test_express_eligible_request_routed_to_express_elevator(self):
        # Both floors in EXPRESS_FLOORS → must go to the express elevator.
        b = self._building()
        assigned = req(b, origin=1, destination=20)
        assert assigned == b.elevators[-1].id

    def test_non_express_request_routed_to_regular_elevator(self):
        # Destination not in EXPRESS_FLOORS → must go to a regular elevator.
        b = self._building()
        assigned = req(b, origin=1, destination=15)
        assert assigned == b.elevators[0].id

    def test_express_elevator_rejects_non_express_floors_via_assign(self):
        # Even if assign_passenger is called directly, express elevator ignores bad floors.
        b = self._building()
        e = b.elevators[-1]
        e.assign_passenger(origin=1, destination=15)
        assert 15 not in e.pickups
        assert not e._pending[1]

    def test_express_full_falls_back_to_regular(self):
        # Fill the express elevator, then send another express-eligible request.
        # The building should fall back to a regular elevator rather than queuing.
        b = Building(
            num_floors=20, num_elevators=2,
            max_capacity=1, express_floors=self.EXPRESS_FLOORS,
        )
        req(b, origin=1, destination=20, pid="p1")  # fills express elevator
        assigned = req(b, origin=10, destination=20, pid="p2")
        assert assigned == b.elevators[0].id  # fell back to regular

    def test_express_elevator_completes_journey_end_to_end(self):
        b = self._building()
        req(b, origin=1, destination=10, pid="p1", tick=0)
        for t in range(20):
            step(b, t)
        j = b.journeys[0]
        assert j.alight_tick is not None
        assert j.elevator_id == b.elevators[-1].id
        assert b.elevators[-1].current_floor == 10


# ---------------------------------------------------------------------------
# Simulation helpers shared by Classes 2 and 3
# ---------------------------------------------------------------------------

def run_sim(
    requests_list,
    num_elevators,
    num_floors,
    max_capacity,
    scheduler,
    express_floors=None,
    on_tick=None,
):
    """Run a 101-tick simulation (ticks 0-100) and return the Building."""
    queue = sorted(
        [Request(time=t, id=pid, source=src, destination=dst)
         for t, pid, src, dst in requests_list],
        key=lambda r: r.time,
    )
    building = Building(
        num_floors=num_floors,
        num_elevators=num_elevators,
        max_capacity=max_capacity,
        scheduler=scheduler,
        express_floors=express_floors,
    )
    for tick in range(101):
        while queue and queue[0].time <= tick:
            r = queue.pop(0)
            building.request(
                origin=r.source, destination=r.destination,
                passenger_id=r.id, tick=tick,
            )
        building.step(tick)
        if on_tick:
            on_tick(tick, building)
    return building


def run_scenario(
    requests_list, num_elevators, num_floors, max_capacity,
    scheduler, express_floors=None,
):
    """Return (completed_count, total_count) after a 101-tick simulation."""
    building = run_sim(
        requests_list, num_elevators, num_floors, max_capacity,
        scheduler, express_floors,
    )
    completed = sum(1 for j in building.journeys if j.alight_tick is not None)
    return completed, len(building.journeys)


# ---------------------------------------------------------------------------
# Class 1: scheduler assignment decisions
# ---------------------------------------------------------------------------

class TestSchedulerBehavior:
    def test_nearest_car_picks_minimum_cost_elevator(self):
        b = Building(num_floors=60, num_elevators=3, max_capacity=10, scheduler="nearest_car")
        b.elevators[0].current_floor = 50
        b.elevators[1].current_floor = 5
        b.elevators[2].current_floor = 30
        assigned = req(b, origin=6, destination=20, pid="p1", tick=0)
        assert assigned == 1

    def test_nearest_car_prefers_elevator_heading_toward_request(self):
        b = Building(num_floors=60, num_elevators=2, max_capacity=10, scheduler="nearest_car")
        b.elevators[0].current_floor = 3
        b.elevators[0].direction = Direction.UP
        b.elevators[0].dropoffs = {10}
        b.elevators[1].current_floor = 12
        b.elevators[1].direction = Direction.DOWN
        b.elevators[1].dropoffs = {1}
        assigned = req(b, origin=8, destination=20, pid="p1", tick=0)
        assert assigned == 0

    def test_round_robin_cycles_through_elevators(self):
        b = Building(num_floors=60, num_elevators=3, max_capacity=10, scheduler="round_robin")
        for i in range(6):
            req(b, origin=1, destination=10, pid=f"p{i}", tick=0)
        ids = [j.elevator_id for j in b.journeys]
        assert ids == [0, 1, 2, 0, 1, 2]

    def test_zone_based_assigns_by_origin_floor(self):
        b = Building(num_floors=60, num_elevators=3, max_capacity=10, scheduler="zone_based")
        a1 = req(b, origin=5,  destination=10, pid="p1", tick=0)
        a2 = req(b, origin=25, destination=30, pid="p2", tick=0)
        a3 = req(b, origin=55, destination=60, pid="p3", tick=0)
        assert a1 == 0
        assert a2 == 1
        assert a3 == 2

    def test_zone_based_falls_back_when_zone_elevator_full(self):
        b = Building(num_floors=20, num_elevators=2, max_capacity=1, scheduler="zone_based")
        req(b, origin=1, destination=5, pid="p1", tick=0)
        assert not b.elevators[0].has_capacity()
        result = req(b, origin=2, destination=8, pid="p2", tick=0)
        assert result is None or result != b.elevators[0].id


# ---------------------------------------------------------------------------
# Class 2: physical and logical simulation invariants
# ---------------------------------------------------------------------------

_OVERFLOW_REQS = [
    (0, "p1", 1, 50), (0, "p2", 1, 40), (0, "p3", 1, 30), (0, "p4", 1, 20),
    (0, "p5", 2, 55), (0, "p6", 2, 45), (0, "p7", 3, 35), (0, "p8", 3, 25),
]

_BIDIR_REQS = [
    (0, "p1", 1, 25), (0, "p2", 25, 1), (0, "p3", 1, 30), (0, "p4", 30, 1),
    (0, "p5", 15, 5), (0, "p6", 5, 20), (5, "p7", 10, 28), (5, "p8", 20, 3),
]


class TestSimulationInvariants:
    def test_board_tick_never_before_request(self):
        building = run_sim(
            _OVERFLOW_REQS, num_elevators=2, num_floors=60,
            max_capacity=2, scheduler="nearest_car",
        )
        for j in building.journeys:
            if j.board_tick is not None:
                assert j.board_tick >= j.request_tick, (
                    f"{j.id}: board_tick={j.board_tick} < request_tick={j.request_tick}"
                )

    def test_travel_time_physically_possible(self):
        building = run_sim(
            _OVERFLOW_REQS, num_elevators=2, num_floors=60,
            max_capacity=2, scheduler="nearest_car",
        )
        for j in building.journeys:
            if j.alight_tick is not None:
                # The elevator boards the passenger and moves one floor in the same tick,
                # so the minimum travel ticks for a direct trip is distance - 1.
                min_possible = max(abs(j.destination - j.origin) - 1, 0)
                actual = j.alight_tick - j.board_tick
                assert actual >= min_possible, (
                    f"{j.id}: travel={actual} < min_possible={min_possible}"
                )

    def test_capacity_never_exceeded_during_simulation(self):
        violations = []

        def check(tick, building):
            for e in building.elevators:
                if e.current_passengers > e.max_capacity:
                    violations.append((tick, e.id, e.current_passengers, e.max_capacity))

        run_sim(
            _OVERFLOW_REQS, num_elevators=2, num_floors=60,
            max_capacity=2, scheduler="nearest_car", on_tick=check,
        )
        assert not violations, f"Capacity exceeded at (tick, elevator_id, passengers, cap): {violations}"

    def test_total_time_equals_wait_plus_travel(self):
        building = run_sim(
            _BIDIR_REQS, num_elevators=3, num_floors=30,
            max_capacity=4, scheduler="nearest_car",
        )
        for j in building.journeys:
            if j.alight_tick is not None:
                assert j.total_time == j.wait_time + j.travel_time, (
                    f"{j.id}: total={j.total_time} != wait={j.wait_time} + travel={j.travel_time}"
                )


# ---------------------------------------------------------------------------
# Class 3: ground-truth completion count regression tests
# ---------------------------------------------------------------------------

_BASELINE_REQS = [(0, "p1", 1, 51), (0, "p2", 1, 37), (10, "p3", 20, 1)]
_SINGLE_REQS   = [
    (0, "p1", 1, 40), (0, "p2", 1, 55), (0, "p3", 5, 20),
    (5, "p4", 30, 1), (10, "p5", 10, 50), (10, "p6", 45, 2),
]
_MANY_REQS  = [(0, "p1", 1, 60), (0, "p2", 30, 1), (0, "p3", 15, 45)]
_SIMUL_REQS = [
    (0, "p1", 1, 5), (0, "p2", 1, 10), (0, "p3", 1, 15),
    (0, "p4", 1, 20), (0, "p5", 1, 8), (0, "p6", 1, 12),
]
_EXPRESS_REQS = [
    (0, "p1", 1, 60), (0, "p2", 1, 25), (0, "p3", 20, 40),
    (5, "p4", 5, 35), (5, "p5", 1, 20), (10, "p6", 40, 1), (10, "p7", 15, 45),
]
_MORNING_RUSH_REQS = [
    (0, "p1",  1,  3), (0, "p2",  1,  5), (0, "p3",  1,  7), (0, "p4",  1,  9),
    (0, "p5",  1, 11), (0, "p6",  1, 13), (0, "p7",  1, 15), (0, "p8",  1, 17),
    (0, "p9",  1, 19), (0, "p10", 1, 21), (0, "p11", 1, 23), (0, "p12", 1, 25),
    (0, "p13", 1, 27), (0, "p14", 1, 29), (0, "p15", 1, 30),
]
_LUNCHTIME_REQS = [
    (0, "p1",  3, 1), (0, "p2",  5, 1), (0, "p3",  7, 1), (0, "p4",  9, 1),
    (0, "p5", 11, 1), (0, "p6", 13, 1), (0, "p7", 15, 1), (0, "p8", 17, 1),
    (0, "p9", 19, 1), (0, "p10", 21, 1), (0, "p11", 23, 1), (0, "p12", 25, 1),
    (0, "p13", 27, 1), (0, "p14", 29, 1), (0, "p15", 30, 1),
]
_TOWNHALL_REQS = [
    (0, "p1",  1, 15), (0, "p2",  3, 15), (0, "p3",  5, 15), (0, "p4",  7, 15),
    (0, "p5",  9, 15), (0, "p6", 11, 15), (0, "p7", 13, 15), (0, "p8", 17, 15),
    (0, "p9", 19, 15), (0, "p10", 21, 15), (0, "p11", 23, 15), (0, "p12", 25, 15),
    (0, "p13", 27, 15), (0, "p14", 29, 15), (0, "p15", 30, 15),
]
_CEO_VISIT_REQS = [
    (0, "ceo",   1, 28), (0, "exec1", 1, 30), (0, "exec2", 1, 25), (0, "exec3", 1, 28),
    (0, "p1",    1,  3), (0, "p2",    1,  5), (0, "p3",    1,  7), (0, "p4",    1,  9),
    (0, "p5",    1, 11), (0, "p6",    1, 13), (0, "p7",    1, 15), (0, "p8",    1, 17),
    (0, "p9",    1, 19), (0, "p10",   1, 21), (0, "p11",   1, 23), (0, "p12",   1, 27),
]

_SCENARIOS = [
    # (scenario_name, reqs, elevators, floors, cap, scheduler, express_floors, done, total)
    ("baseline_nearest_car",          _BASELINE_REQS,      2,  60, 10, "nearest_car", None,              3, 3),
    ("baseline_round_robin",          _BASELINE_REQS,      2,  60, 10, "round_robin", None,              3, 3),
    ("baseline_zone_based",           _BASELINE_REQS,      2,  60, 10, "zone_based",  None,              3, 3),
    ("single_elevator_nearest_car",   _SINGLE_REQS,        1,  60,  5, "nearest_car", None,              3, 6),
    ("single_elevator_round_robin",   _SINGLE_REQS,        1,  60,  5, "round_robin", None,              3, 6),
    ("single_elevator_zone_based",    _SINGLE_REQS,        1,  60,  5, "zone_based",  None,              3, 6),
    ("many_elevators_nearest_car",    _MANY_REQS,          8,  60, 10, "nearest_car", None,              2, 3),
    ("many_elevators_round_robin",    _MANY_REQS,          8,  60, 10, "round_robin", None,              3, 3),
    ("many_elevators_zone_based",     _MANY_REQS,          8,  60, 10, "zone_based",  None,              3, 3),
    ("capacity_overflow_nearest_car", _OVERFLOW_REQS,      2,  60,  2, "nearest_car", None,              5, 8),
    ("capacity_overflow_round_robin", _OVERFLOW_REQS,      2,  60,  2, "round_robin", None,              4, 8),
    ("capacity_overflow_zone_based",  _OVERFLOW_REQS,      2,  60,  2, "zone_based",  None,              2, 8),
    ("simultaneous_nearest_car",      _SIMUL_REQS,         2,  20,  5, "nearest_car", None,              6, 6),
    ("simultaneous_round_robin",      _SIMUL_REQS,         2,  20,  5, "round_robin", None,              6, 6),
    ("simultaneous_zone_based",       _SIMUL_REQS,         2,  20,  5, "zone_based",  None,              6, 6),
    ("bidirectional_nearest_car",     _BIDIR_REQS,         3,  30,  4, "nearest_car", None,              8, 8),
    ("bidirectional_round_robin",     _BIDIR_REQS,         3,  30,  4, "round_robin", None,              8, 8),
    ("bidirectional_zone_based",      _BIDIR_REQS,         3,  30,  4, "zone_based",  None,              8, 8),
    ("express_nearest_car",           _EXPRESS_REQS,       3,  60,  5, "nearest_car", {1,20,40,60},      5, 7),
    ("express_round_robin",           _EXPRESS_REQS,       3,  60,  5, "round_robin", {1,20,40,60},      6, 7),
    ("express_zone_based",            _EXPRESS_REQS,       3,  60,  5, "zone_based",  {1,20,40,60},      4, 7),
    ("morning_rush_nearest_car",      _MORNING_RUSH_REQS,  3,  30,  4, "nearest_car", None,             15, 15),
    ("morning_rush_round_robin",      _MORNING_RUSH_REQS,  3,  30,  4, "round_robin", None,             15, 15),
    ("morning_rush_zone_based",       _MORNING_RUSH_REQS,  3,  30,  4, "zone_based",  None,             12, 15),
    ("lunchtime_nearest_car",         _LUNCHTIME_REQS,     3,  30,  4, "nearest_car", None,             15, 15),
    ("lunchtime_round_robin",         _LUNCHTIME_REQS,     3,  30,  4, "round_robin", None,             15, 15),
    ("lunchtime_zone_based",          _LUNCHTIME_REQS,     3,  30,  4, "zone_based",  None,             13, 15),
    ("townhall_nearest_car",          _TOWNHALL_REQS,      3,  30,  4, "nearest_car", None,             15, 15),
    ("townhall_round_robin",          _TOWNHALL_REQS,      3,  30,  4, "round_robin", None,             15, 15),
    ("townhall_zone_based",           _TOWNHALL_REQS,      3,  30,  4, "zone_based",  None,             15, 15),
    ("ceo_visit_nearest_car",         _CEO_VISIT_REQS,     3,  30,  4, "nearest_car", {1,25,28,30},     16, 16),
    ("ceo_visit_round_robin",         _CEO_VISIT_REQS,     3,  30,  4, "round_robin", {1,25,28,30},     16, 16),
    ("ceo_visit_zone_based",          _CEO_VISIT_REQS,     3,  30,  4, "zone_based",  {1,25,28,30},     12, 16),
]


class TestRegressionScenarios:
    @pytest.mark.parametrize(
        "scenario_name,requests_list,num_elevators,num_floors,max_capacity,scheduler,express_floors,expected_completed,expected_total",
        _SCENARIOS,
        ids=[s[0] for s in _SCENARIOS],
    )
    def test_scenario_completion_count(
        self, scenario_name, requests_list, num_elevators, num_floors,
        max_capacity, scheduler, express_floors,
        expected_completed, expected_total,
    ):
        completed, total = run_scenario(
            requests_list, num_elevators, num_floors, max_capacity,
            scheduler, express_floors,
        )
        assert total == expected_total, (
            f"{scenario_name}: expected {expected_total} total journeys, got {total}"
        )
        assert completed == expected_completed, (
            f"{scenario_name}: expected {expected_completed}/{expected_total} completed, got {completed}/{total}"
        )
