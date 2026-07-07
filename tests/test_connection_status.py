#
# Copyright © 2025 Agora
# This file is part of TEN Framework, an open source project.
# Licensed under the Apache License, Version 2.0, with certain conditions.
# Refer to the "LICENSE" file in the root directory for more information.
#

from ten_ai_base.connection_status import ConnectionStatusMachine
from ten_ai_base.message import ModuleConnectionStatus


def test_happy_path_transitions():
    machine = ConnectionStatusMachine()
    assert machine.status == ModuleConnectionStatus.DISCONNECTED

    connecting = machine.try_connecting()
    assert connecting is not None
    assert connecting.valid
    assert connecting.last == ModuleConnectionStatus.DISCONNECTED
    assert connecting.current == ModuleConnectionStatus.CONNECTING

    connected = machine.try_connected()
    assert connected is not None
    assert connected.valid
    assert connected.current == ModuleConnectionStatus.CONNECTED

    disconnected = machine.try_disconnected(code="1006", message="closed")
    assert disconnected is not None
    assert disconnected.valid
    assert disconnected.code == "1006"
    assert disconnected.message == "closed"
    assert machine.status == ModuleConnectionStatus.DISCONNECTED


def test_idempotent_transitions_return_none():
    machine = ConnectionStatusMachine()
    assert machine.try_disconnected() is None

    machine.try_connecting()
    assert machine.try_connecting() is None

    machine.try_connected()
    assert machine.try_connected() is None


def test_invalid_connected_from_disconnected_still_applies():
    machine = ConnectionStatusMachine()
    transition = machine.try_connected()
    assert transition is not None
    assert not transition.valid
    assert machine.status == ModuleConnectionStatus.CONNECTED


def test_disconnect_code_cleared_on_non_disconnect():
    machine = ConnectionStatusMachine()
    machine.try_connecting()
    connected = machine.try_connected()
    assert connected is not None
    assert connected.code == ""
    assert connected.message == ""
