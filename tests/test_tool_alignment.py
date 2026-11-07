"""Guards on the contracts with the other BrainSTEM tools: the ndx-brainstem namespace version the writer
needs, and the server resolution shared with the API tools (BRAINSTEM_API_URL)."""

import pytest

from brainstem_nwb.errors import ConfigError
from brainstem_nwb.manifest.models import BrainstemExtensionPlan
from brainstem_nwb.nwb.writer import check_extension_version
from brainstem_nwb.retrieval.api import DEFAULT_URL, resolve_url
from brainstem_nwb.retrieval.schemas import schemas_base


def test_older_extension_is_refused():
    required = BrainstemExtensionPlan().namespace_version
    with pytest.raises(ConfigError, match=r"ndx-brainstem 0\.1\.0 is installed"):
        check_extension_version(required, installed="0.1.0")


def test_same_or_newer_extension_is_accepted():
    required = BrainstemExtensionPlan().namespace_version
    check_extension_version(required, installed=required)
    check_extension_version(required, installed="0.9.0")
    check_extension_version(required, installed="1.0.0")


def test_server_resolution_follows_the_api_tools(monkeypatch):
    monkeypatch.delenv("BRAINSTEM_API_URL", raising=False)
    assert resolve_url(None) == DEFAULT_URL
    assert schemas_base(None) == "https://www.brainstem.org/schemas/"
    monkeypatch.setenv("BRAINSTEM_API_URL", "http://127.0.0.1:8000")
    assert resolve_url(None) == "http://127.0.0.1:8000"
    assert schemas_base(None) == "http://127.0.0.1:8000/schemas/"
    assert resolve_url("https://staging.example.org/") == "https://staging.example.org/"
    assert schemas_base("https://staging.example.org") == "https://staging.example.org/schemas/"
