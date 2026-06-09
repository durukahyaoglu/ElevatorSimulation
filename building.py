from elevator import Elevator, Direction
from models import PassengerJourney


class Building:
    def __init__(
        self,
        num_floors: int,
        num_elevators: int,
        max_capacity: int = 10,
        scheduler: str = "nearest_car",
        express_floors: set[int] | None = None,
    ):
        """Initialize the building with a given number of floors, elevators, capacity, and scheduler.

        scheduler:      "nearest_car" (default), "round_robin", or "zone_based"
        express_floors: if provided, the last elevator is designated as express and will
                        only accept requests where both origin and destination are in this set.
        """
        if not isinstance(num_floors, int) or num_floors <= 0:
            raise ValueError(f"num_floors must be a positive integer, got {num_floors!r}")
        if not isinstance(num_elevators, int) or num_elevators <= 0:
            raise ValueError(f"num_elevators must be a positive integer, got {num_elevators!r}")
        if not isinstance(max_capacity, int) or max_capacity <= 0:
            raise ValueError(f"max_capacity must be a positive integer, got {max_capacity!r}")
        self.num_floors = num_floors
        self.elevators = []
        for i in range(num_elevators):
            is_last = (i == num_elevators - 1)
            if express_floors and is_last:
                self.elevators.append(
                    Elevator(i, num_floors, max_capacity,
                             is_express=True, allowed_floors=express_floors)
                )
            else:
                self.elevators.append(Elevator(i, num_floors, max_capacity))
        self.journeys: list[PassengerJourney] = []
        self.waiting: list[PassengerJourney] = []
        self._scheduler = scheduler
        self._rr_index = 0  # pointer for round robin rotation

    def request(self, origin: int, destination: int, passenger_id: str, tick: int) -> int | None:
        """Register a destination dispatch request from a passenger.

        Creates a journey record for the passenger immediately. If an elevator
        is available, assigns it right away and returns the elevator ID. If all
        elevators are full, the journey is held in a waiting queue and retried
        automatically each tick. Returns None when queued rather than assigned.
        """
        journey = PassengerJourney(
            id=passenger_id, request_tick=tick, origin=origin, destination=destination
        )
        self.journeys.append(journey)
        elevator = self._find_best_elevator(origin, destination)
        if elevator is None:
            self.waiting.append(journey)
            return None
        journey.elevator_id = elevator.id
        elevator.assign_passenger(origin, destination, journey)
        return elevator.id

    def _retry_waiting(self):
        """Try to assign any queued journeys now that capacity may have freed up.

        Processes waiting journeys in arrival order (FIFO). Any that still
        cannot be assigned remain in the queue for the next tick.
        """
        still_waiting = []
        for journey in self.waiting:
            elevator = self._find_best_elevator(journey.origin, journey.destination)
            if elevator is None:
                still_waiting.append(journey)
            else:
                journey.elevator_id = elevator.id
                elevator.assign_passenger(journey.origin, journey.destination, journey)
        self.waiting = still_waiting

    def _find_best_elevator(self, origin: int, destination: int) -> Elevator | None:
        """Dispatch to the configured scheduling algorithm."""
        if self._scheduler == "round_robin":
            return self._find_best_elevator_round_robin(origin, destination)
        if self._scheduler == "zone_based":
            return self._find_best_elevator_zone_based(origin, destination)
        return self._find_best_elevator_nearest_car(origin, destination)

    def _find_best_elevator_nearest_car(self, origin: int, destination: int) -> Elevator | None:
        """Nearest Car: return the elevator with the lowest estimated wait + travel time.

        Express-eligible requests (both floors in an express elevator's allowed set) are
        routed to an express elevator first. Only if no express elevator has capacity do
        they fall back to a regular elevator — preserving the intent of express service
        while guaranteeing eventual service.
        """
        express_candidates = [
            e for e in self.elevators
            if e.is_express and e.has_capacity() and e.can_accept(origin, destination)
        ]
        if express_candidates:
            return min(express_candidates, key=lambda e: self._cost(e, origin, destination))

        regular_candidates = [
            e for e in self.elevators
            if not e.is_express and e.has_capacity() and e.can_accept(origin, destination)
        ]
        return min(regular_candidates, key=lambda e: self._cost(e, origin, destination)) if regular_candidates else None

    # -------------------------------------------------------------------------
    # OPTIONAL BONUS: Round Robin scheduler
    # -------------------------------------------------------------------------
    def _find_best_elevator_round_robin(self, origin: int, destination: int) -> Elevator | None:
        """Round Robin (optional bonus): assign requests to elevators in rotation.

        Cycles through elevators in order, skipping any that are at capacity or
        cannot accept the request (e.g. express elevators with restricted floors),
        and returns the next available one. Distributes load evenly across
        elevators without considering distance or direction — simpler but
        generally less efficient than Nearest Car for minimising total time.
        """
        n = len(self.elevators)
        for i in range(n):
            e = self.elevators[(self._rr_index + i) % n]
            if e.has_capacity() and e.can_accept(origin, destination):
                self._rr_index = (self._rr_index + i + 1) % n
                return e
        return None

    # -------------------------------------------------------------------------
    # OPTIONAL BONUS: Zone-based scheduler
    # -------------------------------------------------------------------------
    def _find_best_elevator_zone_based(self, origin: int, destination: int) -> Elevator | None:
        """Zone-based (optional bonus): divide floors into zones, one per elevator.

        The building floors are split into equal contiguous zones. Each
        elevator owns one zone and only serves passengers whose origin floor
        falls within that zone. If the zone elevator is at capacity the
        passenger waits in the queue until it frees up.

        If the zone elevator is express and cannot accept the request (e.g. a
        non-express floor pair lands in the express elevator's zone), the
        dispatcher falls back to any available regular elevator.

        Example with 3 elevators on 60 floors (zone_size = 20):
          E0 → floors  1-20
          E1 → floors 21-40
          E2 → floors 41-60
        """
        n = len(self.elevators)
        zone_size = self.num_floors / n
        zone_index = min(int((origin - 1) / zone_size), n - 1)
        e = self.elevators[zone_index]
        # Express mismatch: zone elevator physically cannot serve these floors.
        # Fall back to any available regular elevator rather than queueing forever.
        if not e.can_accept(origin, destination):
            fallbacks = [
                ev for ev in self.elevators
                if ev is not e and ev.has_capacity() and ev.can_accept(origin, destination)
            ]
            return fallbacks[0] if fallbacks else None

        # Zone elevator can serve these floors — return it if it has capacity, else queue.
        return e if e.has_capacity() else None

    def _cost(self, elevator: Elevator, origin: int, destination: int) -> int:
        """Estimate total_time = wait_time + travel_time for this elevator to serve a request.

        wait_time  — ticks until the elevator reaches the origin floor, following
                     its existing SCAN path through already-queued stops.
        travel_time — ticks from origin to destination after pickup, accounting for
                     any detour caused by stops the elevator still has above/below origin.
        """
        wait_time = elevator.estimate_time_to_floor(origin)
        travel_time = self._estimate_travel_time(elevator, origin, destination)
        return wait_time + travel_time

    def _estimate_travel_time(self, elevator: Elevator, origin: int, destination: int) -> int:
        """Estimate ticks from origin to destination after the elevator picks up the passenger.

        Determines which direction the elevator will be travelling when it arrives at
        origin, then checks whether destination lies ahead (direct path) or behind
        (requires sweeping to the far end of remaining stops first, then reversing).
        """
        if origin == destination:
            return 0

        if elevator.is_idle() or not elevator.destinations:
            dir_at_origin = Direction.UP if destination > origin else Direction.DOWN
        elif elevator.direction == Direction.UP:
            dir_at_origin = Direction.UP if origin >= elevator.current_floor else Direction.DOWN
        else:
            dir_at_origin = Direction.DOWN if origin <= elevator.current_floor else Direction.UP

        if dir_at_origin == Direction.UP:
            if destination > origin:
                return destination - origin
            above = {d for d in elevator.destinations if d > origin}
            far_end = max(above) if above else origin
            return (far_end - origin) + (far_end - destination)
        else:
            if destination < origin:
                return origin - destination
            below = {d for d in elevator.destinations if d < origin}
            far_end = min(below) if below else origin
            return (origin - far_end) + (destination - far_end)

    def step(self, tick: int):
        """Advance the simulation by one tick.

        Retries waiting requests first (capacity may have freed up this tick),
        then moves all elevators one floor.
        """
        self._retry_waiting()
        for elevator in self.elevators:
            elevator.step(tick)

    def status(self):
        """Print the current state of all elevators."""
        for e in self.elevators:
            print(e)
