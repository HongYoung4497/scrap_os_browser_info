#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Iterable, Optional

import mwparserfromhell
import requests
from bs4 import BeautifulSoup

USER_AGENT = "scrap_os_browser_info/1.0 (+https://example.com)"


@dataclass
class ReleaseInfo:
    version: Optional[str]
    version_code: Optional[str]
    release_date: Optional[str]
    source: str


def _request_json(url: str) -> Any:
    response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=30)
    response.raise_for_status()
    return response.json()


def _request_text(url: str) -> str:
    response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=30)
    response.raise_for_status()
    return response.text


def _clean_wikitext(value: str) -> str:
    value = re.sub(r"<ref[^>]*?>.*?</ref>", "", value, flags=re.DOTALL)
    value = re.sub(r"<ref[^/>]*/>", "", value)
    cleaned = mwparserfromhell.parse(value).strip_code()
    return cleaned.strip()


def _parse_wiki_date(value: str) -> Optional[str]:
    match = re.search(r"\{\{Start date\|(\d{4})\|(\d{1,2})\|(\d{1,2})", value)
    if match:
        year, month, day = match.groups()
        return f"{year}-{int(month):02d}-{int(day):02d}"
    cleaned = _clean_wikitext(value)
    return cleaned or None


def _extract_wikitext_field(wikitext: str, keys: Iterable[str]) -> Optional[str]:
    for key in keys:
        pattern = rf"^\|\s*{re.escape(key)}\s*=\s*(.+)$"
        match = re.search(pattern, wikitext, flags=re.MULTILINE)
        if match:
            return match.group(1).strip()
    return None


def _fetch_wikipedia_wikitext(page: str) -> str:
    url = "https://en.wikipedia.org/w/api.php"
    params = {
        "action": "parse",
        "page": page,
        "prop": "wikitext",
        "format": "json",
    }
    response = requests.get(url, params=params, headers={"User-Agent": USER_AGENT}, timeout=30)
    response.raise_for_status()
    data = response.json()
    return data["parse"]["wikitext"]["*"]


def _from_wikipedia(
    page: str,
    stable_version_keys: Iterable[str],
    stable_date_keys: Iterable[str],
    beta_version_keys: Iterable[str],
    beta_date_keys: Iterable[str],
    stable_code_keys: Iterable[str] | None = None,
    beta_code_keys: Iterable[str] | None = None,
) -> dict[str, ReleaseInfo]:
    wikitext = _fetch_wikipedia_wikitext(page)
    stable_version_raw = _extract_wikitext_field(wikitext, stable_version_keys)
    stable_date_raw = _extract_wikitext_field(wikitext, stable_date_keys)
    stable_code_raw = _extract_wikitext_field(wikitext, stable_code_keys or [])
    beta_version_raw = _extract_wikitext_field(wikitext, beta_version_keys)
    beta_date_raw = _extract_wikitext_field(wikitext, beta_date_keys)
    beta_code_raw = _extract_wikitext_field(wikitext, beta_code_keys or [])

    return {
        "stable": ReleaseInfo(
            version=_clean_wikitext(stable_version_raw) if stable_version_raw else None,
            version_code=_clean_wikitext(stable_code_raw)
            if stable_code_raw
            else _clean_wikitext(stable_version_raw) if stable_version_raw else None,
            release_date=_parse_wiki_date(stable_date_raw) if stable_date_raw else None,
            source=f"https://en.wikipedia.org/wiki/{page}",
        ),
        "beta": ReleaseInfo(
            version=_clean_wikitext(beta_version_raw) if beta_version_raw else None,
            version_code=_clean_wikitext(beta_code_raw)
            if beta_code_raw
            else _clean_wikitext(beta_version_raw) if beta_version_raw else None,
            release_date=_parse_wiki_date(beta_date_raw) if beta_date_raw else None,
            source=f"https://en.wikipedia.org/wiki/{page}",
        ),
    }


def fetch_chrome() -> dict[str, ReleaseInfo]:
    def _fetch(channel: str) -> ReleaseInfo:
        data = _request_json(
            f"https://chromiumdash.appspot.com/fetch_milestones?channel={channel}"
        )
        entry = data[0]
        date_key = "stable_date" if channel == "Stable" else "beta_date"
        return ReleaseInfo(
            version=entry.get("version"),
            version_code=str(entry.get("milestone")),
            release_date=entry.get(date_key),
            source="https://chromiumdash.appspot.com/fetch_milestones",
        )

    return {"stable": _fetch("Stable"), "beta": _fetch("Beta")}


def fetch_firefox() -> dict[str, ReleaseInfo]:
    versions = _request_json("https://product-details.mozilla.org/1.0/firefox_versions.json")
    history_stable = _request_json(
        "https://product-details.mozilla.org/1.0/firefox_history_major_releases.json"
    )
    history_dev = _request_json(
        "https://product-details.mozilla.org/1.0/firefox_history_development_releases.json"
    )

    stable_version = versions.get("LATEST_FIREFOX_VERSION")
    beta_version = versions.get("LATEST_FIREFOX_RELEASED_DEVEL_VERSION")

    return {
        "stable": ReleaseInfo(
            version=stable_version,
            version_code=stable_version,
            release_date=history_stable.get(stable_version),
            source="https://product-details.mozilla.org/1.0/firefox_versions.json",
        ),
        "beta": ReleaseInfo(
            version=beta_version,
            version_code=beta_version,
            release_date=history_dev.get(beta_version),
            source="https://product-details.mozilla.org/1.0/firefox_versions.json",
        ),
    }


def fetch_edge() -> dict[str, ReleaseInfo]:
    data = _request_json("https://edgeupdates.microsoft.com/api/products?view=enterprise")
    channels: dict[str, ReleaseInfo] = {}
    for channel_name in ("Stable", "Beta"):
        channel_data = next(
            (
                product
                for product in data
                if product.get("Product") == f"Microsoft Edge {channel_name}"
            ),
            None,
        )
        if not channel_data:
            channels[channel_name.lower()] = ReleaseInfo(
                version=None,
                version_code=None,
                release_date=None,
                source="https://edgeupdates.microsoft.com/api/products?view=enterprise",
            )
            continue
        release = max(
            channel_data.get("Releases", []),
            key=lambda item: item.get("PublishedTime", ""),
        )
        channels[channel_name.lower()] = ReleaseInfo(
            version=release.get("ProductVersion"),
            version_code=str(release.get("ReleaseId")),
            release_date=release.get("PublishedTime"),
            source="https://edgeupdates.microsoft.com/api/products?view=enterprise",
        )
    return {"stable": channels["stable"], "beta": channels["beta"]}


def _parse_opera_listing(url: str) -> tuple[Optional[str], Optional[str]]:
    text = _request_text(url)
    soup = BeautifulSoup(text, "html.parser")
    versions: list[tuple[str, Optional[str]]] = []
    for link in soup.find_all("a"):
        href = link.get("href", "")
        match = re.match(r"(\d+\.\d+(?:\.\d+){1,2})/?", href)
        if match:
            version = match.group(1)
            row_text = link.parent.get_text(" ", strip=True)
            date_match = re.search(r"(\d{4}-\d{2}-\d{2})", row_text)
            date = date_match.group(1) if date_match else None
            versions.append((version, date))
    if not versions:
        return None, None
    versions.sort(key=lambda item: [int(part) for part in item[0].split(".")], reverse=True)
    return versions[0]


def fetch_opera() -> dict[str, ReleaseInfo]:
    stable_version, stable_date = _parse_opera_listing(
        "https://get.geo.opera.com/pub/opera/desktop/"
    )
    beta_version, beta_date = _parse_opera_listing("https://get.geo.opera.com/pub/opera-beta/")
    return {
        "stable": ReleaseInfo(
            version=stable_version,
            version_code=stable_version,
            release_date=stable_date,
            source="https://get.geo.opera.com/pub/opera/desktop/",
        ),
        "beta": ReleaseInfo(
            version=beta_version,
            version_code=beta_version,
            release_date=beta_date,
            source="https://get.geo.opera.com/pub/opera-beta/",
        ),
    }


def fetch_safari() -> dict[str, ReleaseInfo]:
    return _from_wikipedia(
        page="Safari_(web_browser)",
        stable_version_keys=["latest_release_version", "latest_release"],
        stable_date_keys=["latest_release_date", "latest_release_date"],
        beta_version_keys=["latest_preview_version", "latest_beta_version", "latest_release_version"],
        beta_date_keys=["latest_preview_date", "latest_beta_release_date", "latest_release_date"],
    )


def fetch_whale() -> dict[str, ReleaseInfo]:
    return _from_wikipedia(
        page="Whale_(web_browser)",
        stable_version_keys=["latest_release_version", "latest_release"],
        stable_date_keys=["latest_release_date", "latest_release_date"],
        beta_version_keys=["latest_preview_version", "latest_beta_version"],
        beta_date_keys=["latest_preview_date", "latest_beta_release_date"],
    )


def fetch_windows() -> dict[str, ReleaseInfo]:
    return _from_wikipedia(
        page="Windows_11",
        stable_version_keys=["latest_release_version", "latest_release"],
        stable_date_keys=["latest_release_date", "latest_release_date"],
        beta_version_keys=["latest_preview_version", "latest_beta_version"],
        beta_date_keys=["latest_preview_date", "latest_beta_release_date"],
    )


def fetch_macos() -> dict[str, ReleaseInfo]:
    return _from_wikipedia(
        page="macOS",
        stable_version_keys=["latest_release_version", "latest_release"],
        stable_date_keys=["latest_release_date", "latest_release_date"],
        beta_version_keys=["latest_preview_version", "latest_beta_version"],
        beta_date_keys=["latest_preview_date", "latest_beta_release_date"],
    )


def fetch_android() -> dict[str, ReleaseInfo]:
    return _from_wikipedia(
        page="Android_(operating_system)",
        stable_version_keys=["latest_release_version", "latest_release"],
        stable_date_keys=["latest_release_date", "latest_release_date"],
        beta_version_keys=["latest_preview_version", "latest_beta_version"],
        beta_date_keys=["latest_preview_date", "latest_beta_release_date"],
    )


def fetch_ios() -> dict[str, ReleaseInfo]:
    return _from_wikipedia(
        page="iOS",
        stable_version_keys=["latest_release_version", "latest_release"],
        stable_date_keys=["latest_release_date", "latest_release_date"],
        beta_version_keys=["latest_preview_version", "latest_beta_version"],
        beta_date_keys=["latest_preview_date", "latest_beta_release_date"],
    )


def fetch_ipados() -> dict[str, ReleaseInfo]:
    return _from_wikipedia(
        page="iPadOS",
        stable_version_keys=["latest_release_version", "latest_release"],
        stable_date_keys=["latest_release_date", "latest_release_date"],
        beta_version_keys=["latest_preview_version", "latest_beta_version"],
        beta_date_keys=["latest_preview_date", "latest_beta_release_date"],
    )


def collect_all() -> dict[str, Any]:
    return {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "operating_systems": {
            "windows": fetch_windows(),
            "macos": fetch_macos(),
            "android": fetch_android(),
            "ios": fetch_ios(),
            "ipados": fetch_ipados(),
        },
        "browsers": {
            "chrome": fetch_chrome(),
            "firefox": fetch_firefox(),
            "opera": fetch_opera(),
            "edge": fetch_edge(),
            "safari": fetch_safari(),
            "whale": fetch_whale(),
        },
    }


def _serialize(data: dict[str, Any]) -> dict[str, Any]:
    def _convert(item: Any) -> Any:
        if isinstance(item, ReleaseInfo):
            return asdict(item)
        if isinstance(item, dict):
            return {key: _convert(value) for key, value in item.items()}
        return item

    return _convert(data)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Collect latest OS/browser release info for stable and beta channels."
    )
    parser.add_argument(
        "--output",
        "-o",
        default="-",
        help="Output JSON file path (default: stdout).",
    )
    args = parser.parse_args()

    payload = _serialize(collect_all())
    output = json.dumps(payload, ensure_ascii=False, indent=2)

    if args.output == "-":
        print(output)
        return
    with open(args.output, "w", encoding="utf-8") as handle:
        handle.write(output)


if __name__ == "__main__":
    main()
