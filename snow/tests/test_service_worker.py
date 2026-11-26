"""The service worker is a real script: an empty one would install and leave the page with no offline copy."""
import re

from tahoe_snow.config import ROOT


def test_the_service_worker_names_its_cache_and_answers_requests():
    script = (ROOT / "sw.js").read_text()
    assert re.search(r"const VERSION = 'sierra-snow-v\d+';", script)
    assert "addEventListener('fetch'" in script or 'addEventListener("fetch"' in script
    assert len(script) > 5000
