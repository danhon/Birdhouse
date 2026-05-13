"""Tests for BirdNET-Go API client, including date filtering."""

import pytest
import responses as rsps_lib
import requests

from birdhouse.app import fetch_detections_for_date

BASE = "http://localhost:8888"
DATE = "2026-05-12"


def _page(records, total, current_page=1, total_pages=1):
    return {
        "data": records,
        "total": total,
        "limit": 200,
        "offset": 0,
        "current_page": current_page,
        "total_pages": total_pages,
    }


def _det(date, sci="Corvus brachyrhynchos"):
    return {"date": date, "scientificName": sci, "confidence": 0.8,
            "timestamp": f"{date}T08:00:00-07:00", "commonName": "American Crow"}


@rsps_lib.activate
def test_returns_only_records_matching_date():
    today = _det(DATE)
    yesterday = _det("2026-05-11")
    rsps_lib.add(rsps_lib.GET, f"{BASE}/api/v2/detections",
                 json=_page([today, yesterday], total=2))

    session = requests.Session()
    result = fetch_detections_for_date(BASE, DATE, session)

    assert len(result) == 1
    assert result[0]["date"] == DATE


@rsps_lib.activate
def test_returns_empty_when_no_records_match_date():
    rsps_lib.add(rsps_lib.GET, f"{BASE}/api/v2/detections",
                 json=_page([_det("2026-05-11")], total=1))

    session = requests.Session()
    result = fetch_detections_for_date(BASE, DATE, session)

    assert result == []


@rsps_lib.activate
def test_paginates_while_date_matches():
    page1 = [_det(DATE, "Corvus brachyrhynchos")]
    page2 = [_det(DATE, "Haemorhous mexicanus")]
    rsps_lib.add(rsps_lib.GET, f"{BASE}/api/v2/detections",
                 json=_page(page1, total=2, current_page=1, total_pages=2))
    rsps_lib.add(rsps_lib.GET, f"{BASE}/api/v2/detections",
                 json=_page(page2, total=2, current_page=2, total_pages=2))

    session = requests.Session()
    result = fetch_detections_for_date(BASE, DATE, session)

    assert len(result) == 2


@rsps_lib.activate
def test_stops_paginating_when_date_changes():
    page1 = [_det(DATE)]
    page2 = [_det("2026-05-11")]  # slipped past the target date
    rsps_lib.add(rsps_lib.GET, f"{BASE}/api/v2/detections",
                 json=_page(page1, total=2, current_page=1, total_pages=2))
    rsps_lib.add(rsps_lib.GET, f"{BASE}/api/v2/detections",
                 json=_page(page2, total=2, current_page=2, total_pages=2))

    session = requests.Session()
    result = fetch_detections_for_date(BASE, DATE, session)

    assert len(result) == 1
    assert result[0]["date"] == DATE


@rsps_lib.activate
def test_returns_empty_on_request_failure():
    rsps_lib.add(rsps_lib.GET, f"{BASE}/api/v2/detections",
                 body=requests.ConnectionError("unreachable"))

    session = requests.Session()
    result = fetch_detections_for_date(BASE, DATE, session)

    assert result == []
