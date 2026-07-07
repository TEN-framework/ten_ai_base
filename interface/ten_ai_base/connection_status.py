#
# This file is part of TEN Framework, an open source project.
# Licensed under the Apache License, Version 2.0.
# See the LICENSE file for more information.
#
from dataclasses import dataclass

from .message import ModuleConnectionStatus


@dataclass(frozen=True)
class ConnectionStatusTransition:
    current: ModuleConnectionStatus
    last: ModuleConnectionStatus
    code: int = 0
    message: str = ""
    valid: bool = True


class ConnectionStatusMachine:
    """
    Owns connecting / connected / disconnected transitions for long-lived
    vendor connections. Event emission stays with the caller.

    ``_status`` tracks the event sequence for reporting and observation only;
    the authoritative connection state is the vendor's ``is_connected()``.
    Do not treat ``machine.status == CONNECTED`` as proof of a live connection.
    """

    def __init__(
        self,
        initial: ModuleConnectionStatus = ModuleConnectionStatus.DISCONNECTED,
    ) -> None:
        self._status = initial

    @property
    def status(self) -> ModuleConnectionStatus:
        return self._status

    @staticmethod
    def is_valid_transition(
        last_status: ModuleConnectionStatus,
        new_status: ModuleConnectionStatus,
    ) -> bool:
        if last_status == new_status:
            return False

        if new_status == ModuleConnectionStatus.DISCONNECTED:
            return True

        if new_status == ModuleConnectionStatus.CONNECTING:
            return last_status in (
                ModuleConnectionStatus.DISCONNECTED,
                ModuleConnectionStatus.CONNECTED,
            )

        if new_status == ModuleConnectionStatus.CONNECTED:
            return last_status == ModuleConnectionStatus.CONNECTING

        return False

    def try_connecting(self) -> ConnectionStatusTransition | None:
        if self._status == ModuleConnectionStatus.CONNECTING:
            return None
        return self._apply(ModuleConnectionStatus.CONNECTING)

    def try_connected(self) -> ConnectionStatusTransition | None:
        if self._status == ModuleConnectionStatus.CONNECTED:
            return None
        return self._apply(ModuleConnectionStatus.CONNECTED)

    def try_disconnected(
        self, *, code: int = 0, message: str = "closed"
    ) -> ConnectionStatusTransition | None:
        if self._status == ModuleConnectionStatus.DISCONNECTED:
            return None
        return self._apply(
            ModuleConnectionStatus.DISCONNECTED,
            code=code,
            message=message,
        )

    def _apply(
        self,
        new_status: ModuleConnectionStatus,
        *,
        code: int = 0,
        message: str = "",
    ) -> ConnectionStatusTransition:
        last_status = self._status
        valid = self.is_valid_transition(last_status, new_status)
        self._status = new_status
        disconnected = new_status == ModuleConnectionStatus.DISCONNECTED
        return ConnectionStatusTransition(
            current=new_status,
            last=last_status,
            code=code if disconnected else 0,
            message=message if disconnected else "",
            valid=valid,
        )
