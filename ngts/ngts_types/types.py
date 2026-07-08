from typing import Callable

CleanUpT = Callable[[Callable[[], None]], None]
