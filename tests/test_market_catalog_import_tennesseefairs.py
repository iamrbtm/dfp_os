from __future__ import annotations

from datetime import date

from app.services.market_catalog_importers import tennesseefairs as tf
from app.services.market_catalog_importers.runner import run_import

CALENDAR_MD = """[Clay County Fair](https://www.facebook.com/people/Clay-County-Fair/100068311162824/)

--------------------------------------------------------------------------------------

*   MAY 26 - 30
*   215 Arcot Road, celina, tn 38551

[DeKalb County Fair](https://www.dekalbcountyfairtn.com/)

----------------------------------------------------------

*   June 22 - 27
*   100 Fairgrounds drive, alexandria, tn 37012

[Orphan Festival](https://example.com/orphan)

---------------------------------------------

*   September 1 - 3
*   5 Test Lane, nashville, tn 37201
"""

DIRECTORY_MD = """ANDERSON COUNTY FAIR
--------------------

(E) AAA
-------

*   Steve Queener
*   603 Woodland Drive, Clinton, TN 37716
*   (865) 850-2557
*   [srqueener@comcast.net](mailto:%20srqueener@comcast.net)

*   July 13-18, 2026
*   929 Charles G Sevier BLVD, Clinton, TN 37716
*   James Gang Amusements

[Website](http://www.andersoncountyfairtn.com/)

CLAY COUNTY FAIR
---------------

(M) AA
------

*   Jane Doe
*   P.O. Box 123, Celina, TN 38551
*   (931) 555-1234
*   [clayfair@yahoo.com](mailto:%20clayfair@yahoo.com)

*   May 26-30, 2026
*   215 Arcot Road, Celina, TN 38551

[Website](https://www.facebook.com/people/Clay-County-Fair/100068311162824/)
"""


class _FakeFirecrawl:
    def __init__(self, calendar: str, directory: str) -> None:
        self._calendar = calendar
        self._directory = directory

    def scrape_markdown(self, url: str, **_kw: object) -> str:
        if "calendar" in url:
            return self._calendar
        return self._directory


def test_parse_calendar_finds_linked_fairs():
    entries = tf.parse_calendar(CALENDAR_MD)
    assert len(entries) == 3
    clay = next(e for e in entries if e["name"] == "Clay County Fair")
    assert clay["event_url"].endswith("100068311162824/")
    assert clay["calendar_date_text"] == "MAY 26 - 30"
    assert clay["city"] == "Celina"
    assert clay["state"] == "TN"
    assert clay["zip"] == "38551"


def test_parse_directory_extracts_contact_and_classification():
    entries = tf.parse_directory(DIRECTORY_MD)
    clay = next(e for e in entries if e["name"] == "CLAY COUNTY FAIR")
    assert clay["classification"] == "(M) AA"
    assert clay["contact_name"] == "Jane Doe"
    assert clay["phone"] == "(931) 555-1234"
    assert clay["email"] == "clayfair@yahoo.com"
    assert clay["fairgrounds_address"] == "215 Arcot Road, Celina, TN 38551"
    assert clay["date_text"] == "May 26-30, 2026"
    assert clay["website_url"].endswith("100068311162824/")


def test_merge_enriches_directory_with_calendar_link():
    cal = tf.parse_calendar(CALENDAR_MD)
    dire = tf.parse_directory(DIRECTORY_MD)
    records = tf.merge_records(cal, dire)
    # 2 directory (Anderson, Clay) + 2 calendar-only (DeKalb, Orphan)
    assert len(records) == 4
    clay = next(r for r in records if r["name"] == "CLAY COUNTY FAIR")
    assert clay["source"] == "directory+calendar"
    assert clay["event_url"].endswith("100068311162824/")
    orphan = next(r for r in records if r["name"] == "Orphan Festival")
    assert orphan["source"] == "calendar"
    assert orphan["event_url"] == "https://example.com/orphan"


def test_build_payload_maps_anchor_date_and_organizer():
    cal = tf.parse_calendar(CALENDAR_MD)
    dire = tf.parse_directory(DIRECTORY_MD)
    records = tf.merge_records(cal, dire)
    clay = next(r for r in records if r["name"] == "CLAY COUNTY FAIR")
    payload = tf.build_payload(clay)
    assert payload["name"] == "CLAY COUNTY FAIR"
    assert payload["timing"]["anchor_date"] == "2026-05-26"
    assert payload["organizer"]["email"] == "clayfair@yahoo.com"
    assert payload["timing"]["is_recurring"] is True
    assert "TFAI classification: (M) AA" in (payload["description"] or "")


def test_run_import_dry_run_returns_preview_without_db():
    summary = run_import(key="tennesseefairs", 
        client=_FakeFirecrawl(CALENDAR_MD, DIRECTORY_MD),
        dry_run=True,
    )
    assert summary["dry_run"] is True
    assert summary["merged_count"] == 4
    assert summary["created"] == 0
    assert summary["preview"][0]["has_contact"] is True


def test_run_import_commit_persists_listings(app):
    from app.extensions import db
    from app.models import MarketCatalogListing

    before = db.session.query(MarketCatalogListing).count()
    summary = run_import(key="tennesseefairs", 
        client=_FakeFirecrawl(CALENDAR_MD, DIRECTORY_MD),
        dry_run=False,
        actor=None,
    )
    after = db.session.query(MarketCatalogListing).count()
    assert summary["created"] == 4
    assert after - before == 4
    clay = (
        db.session.query(MarketCatalogListing)
        .filter(MarketCatalogListing.name.ilike("clay county fair"))
        .first()
    )
    assert clay is not None
    assert clay.anchor_date == date(2026, 5, 26)
    assert clay.organizer_email == "clayfair@yahoo.com"
    assert clay.is_recurring is True


def test_run_import_commit_is_idempotent(app):
    run_import(key="tennesseefairs", client=_FakeFirecrawl(CALENDAR_MD, DIRECTORY_MD), dry_run=False)
    summary = run_import(key="tennesseefairs", client=_FakeFirecrawl(CALENDAR_MD, DIRECTORY_MD), dry_run=False)
    assert summary["created"] == 0
    assert summary["skipped"] == 4


class _FakeFirecrawlCustom:
    def __init__(self, cal: str, dire: str) -> None:
        self.cal = cal
        self.dire = dire

    def scrape_markdown(self, url: str, **_kw: object) -> str:
        return self.cal if "calendar" in url else self.dire


CAL_A = "[Clay County Fair](https://www.facebook.com/Clay)\n\n------\n\n*   MAY 26 - 30\n*   215 Arcot Road, celina, tn 38551\n"
CAL_B = "[Clay County Fair Days](https://claycountyfairtn.com/)\n\n------\n\n*   May 26-30\n*   215 Arcot Road, celina, tn 38551\n"
CAL_C = "[Clay County Fair](http://claycountyfairtn.com/a)\n\n------\n\n*   May 26-30\n*   215 Arcot Road, celina, tn 38551\n"
CAL_D = "[Clay County Fair Days](https://claycountyfairtn.com/b)\n\n------\n\n*   May 26-30\n*   215 Arcot Road, celina, tn 38551\n"


def test_cross_source_dedup_by_county_state(app):
    run_import(key="tennesseefairs", client=_FakeFirecrawlCustom(CAL_A, ""), dry_run=False)
    summary = run_import(key="tennesseefairs", client=_FakeFirecrawlCustom(CAL_B, ""), dry_run=False)
    assert summary["created"] == 0
    assert summary["skipped"] == 1


def test_cross_source_dedup_by_host(app):
    run_import(key="tennesseefairs", client=_FakeFirecrawlCustom(CAL_C, ""), dry_run=False)
    summary = run_import(key="tennesseefairs", client=_FakeFirecrawlCustom(CAL_D, ""), dry_run=False)
    assert summary["created"] == 0
    assert summary["skipped"] == 1
