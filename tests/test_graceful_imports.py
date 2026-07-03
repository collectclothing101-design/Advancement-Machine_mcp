"""Tests for graceful import fallback when optional dependencies are missing."""
import pytest
from unittest.mock import patch

def test_fallback_when_psutil_missing():
    with patch("advancement_machine.force_multiplier.HAS_PSUTIL", False):
        from advancement_machine.force_multiplier import ForceMultiplier
        fm = ForceMultiplier()
        health = fm.check_health()
        assert health["status"] == "degraded"
        assert "psutil" in health.get("reason", "")

def test_fallback_when_aiohttp_missing():
    with patch("advancement_machine.force_multiplier.HAS_AIOHTTP", False):
        from advancement_machine.force_multiplier import ForceMultiplier
        fm = ForceMultiplier()
        assert fm._resources["aiohttp"] is False

def test_fallback_when_numpy_missing():
    with patch("advancement_machine.force_multiplier.HAS_NUMPY", False):
        from advancement_machine.force_multiplier import ForceMultiplier, ResourceUnavailableError
        fm = ForceMultiplier()
        with pytest.raises(ResourceUnavailableError):
            import asyncio
            asyncio.run(fm.enhance_payload(b"test"))

def test_resource_report_logs_warning(caplog):
    import logging
    caplog.set_level(logging.WARNING)
    with patch("advancement_machine.force_multiplier.HAS_PSUTIL", False):
        with patch("advancement_machine.force_multiplier.HAS_AIOHTTP", False):
            with patch("advancement_machine.force_multiplier.HAS_NUMPY", False):
                from advancement_machine.force_multiplier import ForceMultiplier
                ForceMultiplier()
                assert any("Optional dependencies missing" in record.message for record in caplog.records)

def test_all_dependencies_available():
    from advancement_machine.force_multiplier import HAS_PSUTIL, HAS_AIOHTTP, HAS_NUMPY
    # This test documents availability; it does not fail if deps are absent
    # It exists to verify the flags are booleans
    assert isinstance(HAS_PSUTIL, bool)
    assert isinstance(HAS_AIOHTTP, bool)
    assert isinstance(HAS_NUMPY, bool)