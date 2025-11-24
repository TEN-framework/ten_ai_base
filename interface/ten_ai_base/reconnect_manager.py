#
# This file is part of TEN Framework, an open source project.
# Licensed under the Apache License, Version 2.0.
# See the LICENSE file for more information.
#
import asyncio
from typing import Callable, Awaitable, Optional, Protocol
from .message import ModuleError, ModuleErrorCode, ModuleType


class Logger(Protocol):
    """Logger protocol for type hints."""

    def log_debug(self, msg: str) -> None: ...
    def log_warn(self, msg: str) -> None: ...
    def log_error(self, msg: str) -> None: ...


class ReconnectManager:
    """
    Manages reconnection attempts with fixed retry limit and exponential backoff strategy.

    Features:
    - Fixed retry limit (default: 5 attempts)
    - Exponential backoff strategy: 300ms, 600ms, 1.2s, 2.4s, 4.8s (capped at max_delay)
    - Automatic counter reset after successful connection
    - Thread-safe: can be used concurrently from multiple coroutines
    - Detailed logging for monitoring and debugging

    Example:
        ```python
        # Create reconnect manager
        manager = ReconnectManager(
            max_attempts=5,
            base_delay=0.3,
            max_delay=10.0,
            module_type=ModuleType.ASR,
            logger=some_logger
        )

        # Handle reconnection
        async def establish_connection():
            # Your connection logic here
            await client.connect()

        success = await manager.attempt_reconnect(
            connection_func=establish_connection,
            error_handler=handle_error
        )

        if success:
            # Call this when connection is verified successful
            manager.mark_connection_successful()
        ```

    Note: You must call mark_connection_successful() after verifying the connection
    is actually successful. This resets the attempt counter for future reconnections.
    """

    def __init__(
        self,
        max_attempts: int = 5,
        base_delay: float = 0.3,  # 300 milliseconds
        max_delay: float = 10.0,  # Cap at 10 seconds to prevent overflow
        module_type: ModuleType = ModuleType.ASR,
        logger: Optional[Logger] = None,
    ):
        self.max_attempts = max_attempts
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.module_type = module_type
        self.logger = logger

        # State tracking
        self.attempts = 0
        self._lock = asyncio.Lock()  # Thread safety for concurrent access

    def reset_counter(self):
        """Reset reconnection counter"""
        self.attempts = 0
        if self.logger:
            self.logger.log_debug("Reconnect counter reset")

    def mark_connection_successful(self):
        """Mark connection as successful and reset counter"""
        self.reset_counter()

    def can_retry(self) -> bool:
        """Check if more reconnection attempts are allowed"""
        return self.attempts < self.max_attempts

    def get_attempts_info(self) -> dict:
        """Get current reconnection attempts information"""
        return {
            "current_attempts": self.attempts,
            "max_attempts": self.max_attempts,
            "can_retry": self.can_retry(),
        }

    async def attempt_reconnect(
        self,
        connection_func: Callable[[], Awaitable[None]],
        error_handler: Optional[Callable[[ModuleError], Awaitable[None]]] = None,
    ) -> bool:
        """
        Handle a single reconnection attempt with backoff delay.

        Args:
            connection_func: Async function to establish connection
            error_handler: Optional async function to handle errors

        Returns:
            True if connection function executed successfully, False if failed
            Note: Actual connection success is determined by callback calling
            mark_connection_successful()
        """
        async with self._lock:  # Ensure thread safety for concurrent access
            if not self.can_retry():
                if self.logger:
                    self.logger.log_error(
                        f"Maximum reconnection attempts ({self.max_attempts}) "
                        f"reached. No more attempts allowed."
                    )
                if error_handler:
                    await error_handler(
                        ModuleError(
                            module=self.module_type,
                            code=int(ModuleErrorCode.FATAL_ERROR.value),
                            message=f"Failed to reconnect after {self.max_attempts} attempts",
                        )
                    )
                return False

            self.attempts += 1

            # Calculate exponential backoff delay with cap to prevent overflow
            delay = min(self.base_delay * (2 ** (self.attempts - 1)), self.max_delay)

            if self.logger:
                self.logger.log_warn(
                    f"Attempting reconnection #{self.attempts}/{self.max_attempts} "
                    f"after {delay} seconds delay..."
                )

            try:
                await asyncio.sleep(delay)
                await connection_func()

                # Connection function completed successfully
                # Actual connection success will be determined by callback
                if self.logger:
                    self.logger.log_debug(
                        f"Connection function completed for attempt #{self.attempts}"
                    )
                return True

            except Exception as e:
                if self.logger:
                    self.logger.log_error(
                        f"Reconnection attempt #{self.attempts} failed: {e}"
                    )

                # If this was the last attempt, send error
                if self.attempts >= self.max_attempts:
                    if error_handler:
                        await error_handler(
                            ModuleError(
                                module=self.module_type,
                                code=int(ModuleErrorCode.FATAL_ERROR.value),
                                message=f"All reconnection attempts failed. Last error: {str(e)}",
                            )
                        )

                return False
