import datetime as dt

import pytest

from brainstem_nwb.normalize.identifiers import dandi_label, ncbi_taxon_iri, normalize_rrid
from brainstem_nwb.normalize.kv import key_values, repository_links
from brainstem_nwb.normalize.quantities import Quantity, convert, parse_quantity
from brainstem_nwb.normalize.text import html_to_text, humanize_code, humanize_key
from brainstem_nwb.normalize.timeutil import (
    iso_duration_days,
    isoformat_utc,
    parse_date,
    parse_datetime,
    parse_duration,
)

UTC = dt.timezone.utc


class TestDatetime:
    @pytest.mark.parametrize("text, expected", [
        ("2024-01-01T08:00:00.123Z", dt.datetime(2024, 1, 1, 8, 0, 0, 123000, tzinfo=UTC)),
        ("2024-01-01T08:00:00Z", dt.datetime(2024, 1, 1, 8, tzinfo=UTC)),
        ("2024-01-01T08:00:00", dt.datetime(2024, 1, 1, 8, tzinfo=UTC)),
        ("2024-01-01T08:00:00.000000+00:00", dt.datetime(2024, 1, 1, 8, tzinfo=UTC)),
        ("2024-01-01 08:00", dt.datetime(2024, 1, 1, 8, tzinfo=UTC)),
    ])
    def test_export_forms(self, text, expected):
        assert parse_datetime(text) == expected

    def test_offset_is_kept(self):
        value = parse_datetime("2024-07-01T23:30:00.5+02:00")
        assert value.utcoffset() == dt.timedelta(hours=2)
        assert value.astimezone(UTC) == dt.datetime(2024, 7, 1, 21, 30, 0, 500000, tzinfo=UTC)

    @pytest.mark.parametrize("bad", ["", "yesterday", "2024-13-01T00:00:00Z", None, 5])
    def test_rejects_garbage(self, bad):
        with pytest.raises(ValueError):
            parse_datetime(bad)

    def test_isoformat_utc(self):
        assert isoformat_utc(dt.datetime(2024, 1, 1, 10, tzinfo=dt.timezone(dt.timedelta(hours=2)))) == \
            "2024-01-01T08:00:00Z"

    def test_date(self):
        assert parse_date("2024-02-29") == dt.date(2024, 2, 29)


class TestDuration:
    @pytest.mark.parametrize("text, seconds", [
        ("00:05:00", 300),
        ("0:05:00", 300),
        ("01:02:03.500000", 3723.5),
        ("01:02:03.5", 3723.5),
        ("1 02:00:00", 93600),
        ("-1 23:59:59", -1),
        ("PT1H2M3.5S", 3723.5),
        ("P1DT2H", 93600),
        ("-PT10S", -10),
        (90, 90),
        (1.5, 1.5),
    ])
    def test_forms(self, text, seconds):
        assert parse_duration(text).total_seconds() == pytest.approx(seconds)

    @pytest.mark.parametrize("bad", ["", "P", "ten minutes", True, None])
    def test_rejects(self, bad):
        with pytest.raises(ValueError):
            parse_duration(bad)

    def test_iso_days(self):
        assert iso_duration_days(90) == "P90D"
        with pytest.raises(ValueError):
            iso_duration_days(-1)


class TestQuantities:
    def test_value_unit(self):
        q = parse_quantity({"value": 1.5, "unit": "mm"})
        assert q == Quantity(1.5, "mm")
        assert q.text() == "1.5 mm"

    def test_bare_number_has_no_unit(self):
        q = parse_quantity(20000)
        assert q.legacy_bare_number and q.unit is None
        assert q.text() == "20000 (unit not recorded)"

    def test_empty(self):
        assert parse_quantity({"value": None, "unit": "mm"}) is None
        assert parse_quantity("text") is None
        assert parse_quantity(True) is None

    @pytest.mark.parametrize("raw, unit, expected", [
        ({"value": 0.473, "unit": "µm"}, "nm", 473),
        ({"value": 20, "unit": "kHz"}, "Hz", 20000),
        ({"value": 0.195, "unit": "µV"}, "uV", 0.195),
        ({"value": 473, "unit": "nm"}, "nm", 473),
    ])
    def test_convert(self, raw, unit, expected):
        assert convert(parse_quantity(raw), unit) == pytest.approx(expected)

    def test_convert_refuses_other_dimension_or_unknown(self):
        with pytest.raises(ValueError):
            convert(parse_quantity({"value": 1, "unit": "mm"}), "Hz")
        with pytest.raises(ValueError):
            convert(parse_quantity({"value": 1, "unit": "furlong"}), "m")
        with pytest.raises(ValueError):
            convert(parse_quantity(5), "nm")


class TestText:
    def test_html(self):
        assert html_to_text("<p>One &amp; <b>two</b></p><p>Three</p>") == "One & two\n\nThree"
        assert html_to_text("<ul><li>a</li><li>b</li></ul>") == "- a\n- b"
        assert html_to_text(None) == ""
        assert html_to_text("plain") == "plain"

    def test_humanize(self):
        assert humanize_key("postInfusionDwell") == "post infusion dwell"
        assert humanize_code("bolus_injection") == "bolus injection"
        assert humanize_code("SiliconProbeImplant") == "silicon probe implant"


class TestKeyValues:
    def test_list_and_dict_forms(self):
        assert key_values([{"key": "a", "value": 1}, {"key": "", "value": "x"}, {"value": "y"}]) == [("a", "1")]
        assert key_values({"cage": "C-12", "diet": None, "n": {"x": 1}}) == [
            ("cage", "C-12"), ("diet", ""), ("n", '{"x":1}')]
        assert key_values(None) == []

    def test_repository_links(self):
        assert repository_links([{"repository": "DANDI", "url": "u"}, {"repository": "x"}]) == [("DANDI", "u")]
        assert repository_links("nope") == []


class TestIdentifiers:
    @pytest.mark.parametrize("fields, expected", [
        ({"external_identifiers": [{"source": "NCBI", "id": "10090"}]}, "10090"),
        ({"rrid": "RRID:NCBITaxon_10116"}, "10116"),
        ({"rrid": "RRID:NCBI_txid9606"}, "9606"),
        ({"external_identifiers": [{"source": "NCBI", "url": "https://x/wwwtax.cgi?id=7955"}]}, "7955"),
        ({"name": "Mus musculus"}, None),
    ])
    def test_ncbi_taxon(self, fields, expected):
        iri = ncbi_taxon_iri(fields)
        assert iri == (f"http://purl.obolibrary.org/obo/NCBITaxon_{expected}" if expected else None)

    def test_rrid(self):
        assert normalize_rrid("RRID: IMSR_JAX:000664") == "RRID:IMSR_JAX:000664"
        assert normalize_rrid("IMSR_JAX:000664") == "RRID:IMSR_JAX:000664"
        assert normalize_rrid("") is None

    def test_dandi_label(self):
        assert dandi_label("Edge/Case #1") == "Edge-Case-1"
        assert dandi_label("SM01_2024-04-01") == "SM01-2024-04-01"
        assert dandi_label("///") == "unnamed"
