import logging
from unittest.mock import MagicMock, patch

from app.services.log_sink import LogSink


def test_disabled_sink_is_noop():
    sink = LogSink(host=None, port=514, proto="tcp", facility="local0")
    assert sink.enabled is False
    # emit must not raise and must do nothing visible.
    sink.emit("refresh.success", run_id=1, provider_id=2)


def test_unknown_proto_disables_sink():
    sink = LogSink(host="127.0.0.1", port=514, proto="gopher", facility="local0")
    assert sink.enabled is False
    sink.emit("refresh.success", run_id=1)


def test_emit_calls_handler_emit_once_with_quoted_message():
    sink = LogSink(host=None, port=514, proto="tcp", facility="local0")
    sink._handler = MagicMock()
    sink.emit("refresh.success", run_id=42, provider_id=7, provider_name="my-vpn")
    assert sink._handler.emit.call_count == 1
    record = sink._handler.emit.call_args[0][0]
    assert isinstance(record, logging.LogRecord)
    assert "refresh.success" in record.msg
    assert "run_id=42" in record.msg
    assert "provider_id=7" in record.msg


def test_emit_quotes_values_with_spaces():
    sink = LogSink(host=None, port=514, proto="tcp", facility="local0")
    sink._handler = MagicMock()
    sink.emit("refresh.success", provider_name='has "quote" and space')
    record = sink._handler.emit.call_args[0][0]
    assert '"has \\"quote\\" and space"' in record.msg


def test_emit_swallows_network_errors():
    sink = LogSink(host=None, port=514, proto="tcp", facility="local0")
    sink._handler = MagicMock()
    sink._handler.emit.side_effect = OSError("rsyslog down")
    # Must not raise.
    sink.emit("refresh.success", run_id=1)


def test_close_releases_handler():
    sink = LogSink(host=None, port=514, proto="tcp", facility="local0")
    handler = MagicMock()
    sink._handler = handler
    sink.close()
    handler.close.assert_called_once()
    assert sink._handler is None
    # Second close is safe.
    sink.close()
