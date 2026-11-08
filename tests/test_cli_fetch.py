import gzip
import json
from typing import ClassVar

import pytest
from click.testing import CliRunner

from brainstem_nwb.cli import main
from brainstem_nwb.errors import AuthRequired, RetrievalError
from brainstem_nwb.retrieval import api

from .conftest import EXPORTS, scenario, scenario_file


def run(*args, **kwargs):
    return CliRunner().invoke(main, list(args), catch_exceptions=False, **kwargs)


class TestCli:
    def test_export(self, tmp_path):
        result = run("export", "--export-file", str(scenario_file("ephys")), "-o", str(tmp_path))
        assert result.exit_code == 0, result.output
        assert "written: 1" in result.output and "Validation: 0 error(s)" in result.output

    def test_export_json_and_partial_exit(self, tmp_path):
        result = run("export", "--export-file", str(scenario_file("multisession")), "-o", str(tmp_path), "--json")
        assert result.exit_code == 1
        payload = json.loads(result.output)
        assert payload["summary"]["unit_errors"] == 3 and payload["exit_code"] == 1

    def test_export_session_and_config(self, tmp_path):
        config = tmp_path / "c.toml"
        config.write_text('[nwbfile]\nexperimenter = ["Doe, Jane"]\nlab = "L"\ninstitution = "I"\n')
        result = run("export", "--export-file", str(scenario_file("multisession")), "-o", str(tmp_path / "o"),
                     "--session", "SM05_day1", "--config", str(config), "--reproducible")
        assert result.exit_code == 0, result.output
        manifest = json.loads((tmp_path / "o" / "brainstem-nwb-manifest.json").read_text())
        assert manifest["units"][0]["nwb"]["nwbfile"]["experimenter"] == ["Doe, Jane"]

    def test_bad_config_is_a_usage_error(self, tmp_path):
        config = tmp_path / "c.toml"
        config.write_text("[nope]\n")
        result = run("export", "--export-file", str(scenario_file("ephys")), "-o", str(tmp_path), "--config",
                     str(config))
        assert result.exit_code == 2 and "unknown section" in result.output

    def test_bad_export_file(self, tmp_path):
        bad = tmp_path / "bad.json"
        bad.write_text('{"subjects": []}')
        result = run("export", "--export-file", str(bad), "-o", str(tmp_path / "o"))
        assert result.exit_code == 2 and "not a BrainSTEM project export" in result.output

    def test_needs_a_source(self, tmp_path):
        result = CliRunner().invoke(main, ["export", "-o", str(tmp_path)])
        assert result.exit_code == 2

    def test_manifest_command(self, tmp_path):
        result = run("manifest", "--export-file", str(scenario_file("ephys")), "-o", str(tmp_path / "m.json"))
        assert result.exit_code == 0 and (tmp_path / "m.json").exists()
        assert not list(tmp_path.glob("**/*.nwb"))

    def test_validate_command(self, tmp_path):
        run("export", "--export-file", str(scenario_file("ephys")), "-o", str(tmp_path), "--no-validate")
        result = run("validate", str(tmp_path))
        assert result.exit_code == 0 and "0 error(s)" in result.output
        result = run("validate", str(tmp_path), "--fail-on", "warning", "--inspector-config", "none")
        assert result.exit_code == 0

    def test_mapping_and_schema_commands(self, tmp_path):
        result = run("mapping")
        assert result.output.startswith("# BrainSTEM to NWB mapping specification")
        rules = json.loads(run("mapping", "--format", "json").output)
        assert any(rule["id"] == "subject.species" for rule in rules)
        stale = tmp_path / "spec.md"
        stale.write_text("old")
        assert CliRunner().invoke(main, ["mapping", "--check", str(stale)]).exit_code == 1
        schema = json.loads(run("schema", "manifest").output)
        assert schema["title"].startswith("brainstem-nwb conversion manifest")

    def test_version(self):
        assert "brainstem-nwb, version" in run("--version").output


class FakeClient:
    def __init__(self, payload=None, error=None):
        self.payload, self.error, self.calls = payload, error, []

    def export_project(self, project_id, background=False):
        self.calls.append((project_id, background))
        if self.error:
            raise self.error
        return self.payload


class TestFetch:
    def test_fetch_and_save(self, tmp_path):
        payload = scenario("ephys")
        client = FakeClient(payload)
        export = api.fetch_export("p1", client=client, save_to=tmp_path / "e.json.gz")
        assert client.calls == [("p1", True)]
        assert export.source.kind == "api" and export.source.host == "www.brainstem.org"
        assert json.loads(gzip.decompress((tmp_path / "e.json.gz").read_bytes())) == payload

    def test_errors_are_translated(self):
        class AuthenticationError(Exception):
            pass

        class ExportError(Exception):
            pass

        with pytest.raises(AuthRequired):
            api.fetch_export("p", client=FakeClient(error=AuthenticationError("401")))
        with pytest.raises(RetrievalError, match="needs contributor"):
            api.fetch_export("p", client=FakeClient(error=ExportError("needs contributor access")))
        with pytest.raises(RetrievalError):
            api.fetch_export("p", client=FakeClient(error=ConnectionError("down")))

    def test_no_token_does_not_block(self, monkeypatch):
        monkeypatch.setattr(api, "_cached_token_exists", lambda: False)
        with pytest.raises(AuthRequired, match="no BrainSTEM token"):
            api.make_client(token=None, allow_device_flow=False)

    def test_old_api_tools(self, monkeypatch):
        import brainstem_api_tools

        class OldClient:
            pass

        monkeypatch.setattr(brainstem_api_tools, "BrainstemClient", OldClient)
        with pytest.raises(RetrievalError, match="export_project"):
            api.make_client(token="t")

    def test_export_project_fetches_and_keeps_the_export(self, tmp_path, monkeypatch):
        payload = scenario("ephys")
        project_id = payload["export_info"]["project_id"]
        monkeypatch.setattr(api, "make_client", lambda **kwargs: FakeClient(payload))
        from brainstem_nwb import export_project

        result = export_project(project_id, tmp_path, token="secret-token")
        assert result.exit_code == 0
        saved = list((tmp_path / "source").glob("brainstem-export-*.json.gz"))
        assert len(saved) == 1 and result.manifest.source.name == saved[0].name
        assert "secret-token" not in (tmp_path / "brainstem-nwb-manifest.json").read_text()

    def test_cli_auth_failure_exit_code(self, tmp_path, monkeypatch):
        monkeypatch.setattr(api, "_cached_token_exists", lambda: False)
        monkeypatch.delenv("BRAINSTEM_API_TOKEN", raising=False)
        result = CliRunner().invoke(main, ["export", "--project", "p", "-o", str(tmp_path), "--no-device-flow"])
        assert result.exit_code == 3 and "no BrainSTEM token" in result.output


class TestWithRealClient:
    """brainstem-nwb against the installed BrainstemClient; only the HTTP request is replaced."""

    @pytest.fixture
    def client(self):
        brainstem_api_tools = pytest.importorskip("brainstem_api_tools")
        client = brainstem_api_tools.BrainstemClient(token="test-token", url="https://example.org/")
        if not hasattr(client, "export_session"):
            pytest.skip("installed brainstem_python_api_tools has no export_session")
        return client

    @staticmethod
    def respond(monkeypatch, payload, status=200):
        import requests

        calls = []

        class Response:
            status_code = status
            ok = status < 400
            headers: ClassVar[dict[str, str]] = {"Content-Type": "application/json"}
            reason = "test"

            def json(self):
                return payload

            def raise_for_status(self):
                raise requests.HTTPError(str(status))

        def fake_get(url, **kwargs):
            calls.append(url)
            return Response()

        monkeypatch.setattr(requests, "get", fake_get)
        return calls

    def test_session_export(self, client, monkeypatch, tmp_path):
        payload = json.loads((EXPORTS / "server_contract_2_2_session.json").read_text())
        session_id = payload["export_info"]["session_id"]
        calls = self.respond(monkeypatch, payload)
        export = api.fetch_export(session_id=session_id, client=client, background=False)
        assert calls == [f"https://example.org/api/private/stem/session/{session_id}/export/"]
        assert export.scope == "session" and export.source.kind == "api"

    def test_project_export(self, client, monkeypatch):
        payload = json.loads((EXPORTS / "server_contract_2_2.json").read_text())
        project_id = payload["export_info"]["project_id"]
        calls = self.respond(monkeypatch, payload)
        export = api.fetch_export(project_id, client=client, background=False)
        assert calls == [f"https://example.org/api/private/stem/project/{project_id}/export/"]
        assert export.scope == "project"

    def test_no_read_access(self, client, monkeypatch):
        self.respond(monkeypatch, {"detail": "Not found."}, status=404)
        with pytest.raises(RetrievalError, match="read access"):
            api.fetch_export(session_id="00000000-0000-0000-0000-000000000000", client=client, background=False)
