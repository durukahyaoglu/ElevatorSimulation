from dataclasses import dataclass


@dataclass
class Request:
    """A single passenger elevator request."""
    time: int        # simulation tick when the request is made
    id: str          # unique passenger identifier
    source: int      # floor the passenger is currently on
    destination: int # floor the passenger wants to reach


@dataclass
class PassengerJourney:
    """Tracks the full lifecycle of one passenger through the simulation."""
    id: str
    request_tick: int
    origin: int
    destination: int
    board_tick: int | None = None      # tick when passenger boarded at origin
    alight_tick: int | None = None     # tick when passenger alighted at destination
    elevator_id: int | None = None     # elevator assigned to this passenger

    @property
    def wait_time(self) -> int | None:
        """Ticks from request to boarding. None if passenger never boarded."""
        if self.board_tick is None:
            return None
        return self.board_tick - self.request_tick

    @property
    def travel_time(self) -> int | None:
        """Ticks from boarding to alighting. None if journey incomplete."""
        if self.board_tick is None or self.alight_tick is None:
            return None
        return self.alight_tick - self.board_tick

    @property
    def total_time(self) -> int | None:
        """Ticks from request to alighting. None if journey incomplete."""
        if self.alight_tick is None:
            return None
        return self.alight_tick - self.request_tick
