import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from elevator import Elevator, Direction
from building import Building


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
