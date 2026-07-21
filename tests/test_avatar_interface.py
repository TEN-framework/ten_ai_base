import importlib.util
import json
from pathlib import Path


_ROOT = Path(__file__).parents[1]


def _module_metric_key():
    message_path = _ROOT / "interface" / "ten_ai_base" / "message.py"
    spec = importlib.util.spec_from_file_location("ten_ai_base_message", message_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.ModuleMetricKey


def _avatar_interface() -> dict:
    interface_path = _ROOT / "api" / "avatar-interface.json"
    return json.loads(interface_path.read_text(encoding="utf-8"))


def _avatar_data_out() -> dict[str, dict]:
    return {item["name"]: item for item in _avatar_interface()["data_out"]}


def _metadata_properties(data_out: dict) -> dict:
    return data_out["property"]["properties"]["metadata"]["properties"]


def test_avatar_reporting_interface_contract() -> None:
    data_out = _avatar_data_out()

    assert {"error", "metrics", "connection_status_changed"} <= data_out.keys()
    for name in ("error", "metrics", "connection_status_changed"):
        vendor_metadata = _metadata_properties(data_out[name])["vendor_metadata"]
        assert vendor_metadata == {"type": "object", "properties": {}}

    status_properties = data_out["connection_status_changed"]["property"][
        "properties"
    ]
    assert {
        "id",
        "module",
        "vendor_info",
        "current",
        "last",
        "code",
        "message",
        "metadata",
    } <= status_properties.keys()


def test_avatar_audio_frame_accepts_upstream_vendor_metadata() -> None:
    pcm_frame = _avatar_interface()["audio_frame_in"][0]
    metadata = pcm_frame["property"]["properties"]["metadata"]["properties"]

    assert metadata["vendor_metadata"] == {"type": "object", "properties": {}}


def test_avatar_audio_duration_metric_keys() -> None:
    metric_keys = {key.value for key in _module_metric_key()}

    assert "recv_audio_duration" in metric_keys
    assert "total_recv_audio_duration" in metric_keys
