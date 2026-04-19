from enum import Enum, auto


class FaultPoint(Enum):
    PRE_SUBMIT = auto()
    POST_SUBMIT_PRE_FILL = auto()
    OPEN_POSITION_PRE_CLOSE = auto()
    POST_CLOSE_PRE_FEEDBACK = auto()
    REDIS_UNAVAILABLE = auto()
    DUCKDB_UNAVAILABLE = auto()


class FaultInjector:
    def __init__(self, point: FaultPoint | None = None):
        self.point = point

    def apply_and_run(self, strategy) -> None:
        """Inject the selected fault into the mocked or actual strategy."""
        if self.point == FaultPoint.PRE_SUBMIT:
            # We fail before calling submit_order
            raise Exception("Injected PRE_SUBMIT fault")
        
        elif self.point == FaultPoint.POST_SUBMIT_PRE_FILL:
            strategy.submit_order()
            raise Exception("Injected POST_SUBMIT_PRE_FILL fault")
            
        elif self.point == FaultPoint.OPEN_POSITION_PRE_CLOSE:
            strategy.submit_order()
            strategy.on_fill()
            raise Exception("Injected OPEN_POSITION_PRE_CLOSE fault")
            
        elif self.point == FaultPoint.POST_CLOSE_PRE_FEEDBACK:
            strategy.submit_order()
            strategy.on_fill()
            strategy.close_position()
            raise Exception("Injected POST_CLOSE_PRE_FEEDBACK fault")
            
        elif self.point == FaultPoint.REDIS_UNAVAILABLE:
            raise Exception("Injected REDIS_UNAVAILABLE fault")
            
        elif self.point == FaultPoint.DUCKDB_UNAVAILABLE:
            raise Exception("Injected DUCKDB_UNAVAILABLE fault")
            
        else:
            # No fault
            strategy.submit_order()
            strategy.on_fill()
            strategy.close_position()
