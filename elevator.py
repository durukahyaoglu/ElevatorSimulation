from enum import Enum
from collections import defaultdict
from models import PassengerJourney


class Direction(Enum):
    """Represents the movement direction of an elevator."""
    UP = "UP"
    DOWN = "DOWN"
    IDLE = "IDLE"


class Elevator:
    def __init__(
        self,
        elevator_id: int,
        total_floors: int,
        max_capacity: int,
        is_express: bool = False,
        allowed_floors: set[int] | None = None,
    ):
        """Initialize an elevator at floor 1 in an idle state with a passenger cap.

        is_express:     if True, this elevator only stops at floors in allowed_floors.
        allowed_floors: the set of floors an express elevator will accept; ignored when
                        is_express is False.
        """
        self.id = elevator_id
        self.current_floor = 1
        self.direction = Direction.IDLE
        self.total_floors = total_floors
        self.max_capacity = max_capacity
        self.is_express = is_express
        self.allowed_floors: set[int] = allowed_floors or set()
        self.current_passengers = 0
        self.floors_traveled = 0   # total floors moved over the simulation
        self.pickups: set[int] = set()
        self.dropoffs: set[int] = set()
        # Maps origin floor → journeys waiting to board; destination is activated on boarding.
        self._pending: dict[int, list[PassengerJourney]] = defaultdict(list)
        # Maps destination floor → journeys onboard heading there.
        self._dropoff_journeys: dict[int, list[PassengerJourney]] = defaultdict(list)

    def can_accept(self, origin: int, destination: int) -> bool:
        """Return True if this elevator can serve the given origin-destination pair.

        Regular elevators accept all valid floor pairs. Express elevators only
        accept requests where both origin and destination are in allowed_floors.
        """
        if not self.is_express:
            return True
        return origin in self.allowed_floors and destination in self.allowed_floors

    @property
    def destinations(self) -> set[int]:
        """All floors this elevator still needs to visit."""
        return self.pickups | self.dropoffs

    def assign_passenger(self, origin: int, destination: int, journey: PassengerJourney | None = None):
        """Queue a passenger for pickup at origin and dropoff at destination.

        Only the origin is added as an active stop immediately. The destination
        is held in a pending map and only activated once the passenger boards,
        preventing the elevator from servicing a dropoff before the pickup.
        A journey object may be passed to record board/alight timestamps; if
        omitted a throwaway one is created (useful in tests).
        Express elevators silently reject requests for floors outside allowed_floors.
        """
        if not self.can_accept(origin, destination):
            return
        if 1 <= origin <= self.total_floors and 1 <= destination <= self.total_floors:
            if journey is None:
                journey = PassengerJourney(id="_", request_tick=0, origin=origin, destination=destination)
            self.pickups.add(origin)
            self._pending[origin].append(journey)

    def has_capacity(self) -> bool:
        """Return True if the elevator can take on another passenger.

        Counts boarded passengers plus those with pending (not yet boarded) pickups.
        """
        pending_count = sum(len(js) for js in self._pending.values())
        return self.current_passengers + pending_count < self.max_capacity

    def _service_floor(self, tick: int):
        """Board or alight passengers at the current floor and record timestamps.

        On a pickup floor: board all waiting passengers, record their board tick,
        and activate their destination floors. On a dropoff floor: alight all
        passengers headed here and record their alight tick.
        """
        if self.current_floor in self.pickups:
            self.pickups.discard(self.current_floor)
            for journey in self._pending.pop(self.current_floor, []):
                journey.board_tick = tick
                self.current_passengers += 1
                self.dropoffs.add(journey.destination)
                self._dropoff_journeys[journey.destination].append(journey)

        if self.current_floor in self.dropoffs:
            for journey in self._dropoff_journeys.pop(self.current_floor, []):
                journey.alight_tick = tick
                self.current_passengers -= 1
            self.dropoffs.discard(self.current_floor)

    def step(self, tick: int):
        """Advance the elevator by one floor toward its nearest destination.

        Services the current floor first (boarding/alighting), then moves one
        floor in the current direction. Reassesses direction after each move.
        """
        if not self.destinations:
            self.direction = Direction.IDLE
            return

        # Service the current floor before moving
        self._service_floor(tick)

        if not self.destinations:
            self.direction = Direction.IDLE
            return

        # If idle, start moving toward the closest destination.
        # Ties (equal distance above and below) are broken by preferring the lower floor.
        if self.direction == Direction.IDLE:
            target = min(self.destinations, key=lambda f: (abs(f - self.current_floor), f))
            self.direction = Direction.UP if target > self.current_floor else Direction.DOWN

        # Move one floor in the current direction
        if self.direction == Direction.UP:
            self.current_floor += 1
            self.floors_traveled += 1
        elif self.direction == Direction.DOWN:
            self.current_floor -= 1
            self.floors_traveled += 1

        # Service the new floor after arriving
        self._service_floor(tick)

        # Update direction based on remaining destinations
        if not self.destinations:
            self.direction = Direction.IDLE
        elif not any(f > self.current_floor for f in self.destinations):
            self.direction = Direction.DOWN
        elif not any(f < self.current_floor for f in self.destinations):
            self.direction = Direction.UP

    def estimate_time_to_floor(self, target: int) -> int:
        """Estimate ticks to reach target floor following SCAN order.

        If idle, cost is pure distance. If moving, the elevator finishes its
        current sweep before reversing — so a target behind the current direction
        requires going to the far end first, then coming back.
        """
        if self.is_idle() or not self.destinations:
            return abs(self.current_floor - target)
        if self.direction == Direction.UP:
            if target >= self.current_floor:
                return target - self.current_floor
            # Must sweep to the highest queued stop, then come down to target
            highest = max(self.destinations)
            return (highest - self.current_floor) + (highest - target)
        else:  # DOWN
            if target <= self.current_floor:
                return self.current_floor - target
            # Must sweep to the lowest queued stop, then go up to target
            lowest = min(self.destinations)
            return (self.current_floor - lowest) + (target - lowest)

    def is_idle(self) -> bool:
        """Return True if the elevator has no destinations and is not moving."""
        return self.direction == Direction.IDLE and not self.destinations

    def __repr__(self):
        """Return a readable string showing the elevator's current state."""
        express = f", express={sorted(self.allowed_floors)}" if self.is_express else ""
        return (
            f"Elevator(id={self.id}, floor={self.current_floor}, "
            f"direction={self.direction.value}, "
            f"passengers={self.current_passengers}/{self.max_capacity}, "
            f"destinations={sorted(self.destinations)}{express})"
        )
