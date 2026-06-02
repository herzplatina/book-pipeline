"""Unit tests for modules/m4_nonprofits.py — all external I/O is mocked."""

from unittest.mock import MagicMock, patch

import modules.m4_nonprofits as m4
from config.settings import LISTENNOTES_QUERIES, NONPROFIT_URLS


# ---------------------------------------------------------------------------
# _archetype_for_url
# ---------------------------------------------------------------------------


def test_archetype_for_defyventures():
    assert (
        m4._archetype_for_url("https://defyventures.org/alumni-stories/") == "criminal"
    )


def test_archetype_for_lifeafterhate():
    assert m4._archetype_for_url("https://lifeafterhate.org/our-team/") == "extremist"


def test_archetype_for_moonshotcve():
    assert m4._archetype_for_url("https://moonshotcve.com/people/") == "extremist"


def test_archetype_default_is_criminal():
    assert m4._archetype_for_url("https://unknown-nonprofit.org/stories/") == "criminal"


# ---------------------------------------------------------------------------
# _extract_story_links
# ---------------------------------------------------------------------------


def test_extract_story_links_finds_story_paths():
    html = """
    <html><body>
      <a href="/stories/jane-smith">Jane's story</a>
      <a href="/about">About us</a>
      <a href="/stories/john-doe">John's story</a>
    </body></html>
    """
    links = m4._extract_story_links("https://defyventures.org/alumni-stories/", html)
    assert any("jane-smith" in link for link in links)
    assert any("john-doe" in link for link in links)
    assert not any(link.endswith("/about") for link in links)


def test_extract_story_links_strips_query_and_fragment():
    html = '<html><body><a href="/stories/jane?ref=home#section">Jane</a></body></html>'
    links = m4._extract_story_links("https://defyventures.org/alumni-stories/", html)
    assert all("?" not in link and "#" not in link for link in links)


def test_extract_story_links_ignores_external_domains():
    html = '<html><body><a href="https://twitter.com/someone">Twitter</a></body></html>'
    links = m4._extract_story_links("https://defyventures.org/alumni-stories/", html)
    assert links == []


def test_extract_story_links_empty_html():
    links = m4._extract_story_links("https://defyventures.org/", "<html></html>")
    assert links == []


# ---------------------------------------------------------------------------
# _scrape_nonprofit
# ---------------------------------------------------------------------------


@patch("modules.m4_nonprofits.time.sleep")
@patch("modules.m4_nonprofits._fetch_article_text")
@patch("modules.m4_nonprofits._fetch_page")
def test_scrape_nonprofit_returns_leads(mock_page, mock_article, mock_sleep):
    mock_page.return_value = (
        '<html><body><a href="/stories/jane">Jane</a></body></html>'
    )
    mock_article.return_value = "Jane's full transformation story."

    leads = m4._scrape_nonprofit("https://defyventures.org/alumni-stories/")

    assert len(leads) == 1
    assert leads[0]["Source"] == "nonprofit"
    assert leads[0]["Archetype"] == "criminal"
    assert "Jane's full transformation story." in leads[0]["_content"]


@patch("modules.m4_nonprofits._fetch_page")
def test_scrape_nonprofit_empty_page_returns_nothing(mock_page):
    mock_page.return_value = ""
    leads = m4._scrape_nonprofit("https://defyventures.org/alumni-stories/")
    assert leads == []


@patch("modules.m4_nonprofits.time.sleep")
@patch("modules.m4_nonprofits._fetch_article_text")
@patch("modules.m4_nonprofits._fetch_page")
def test_scrape_nonprofit_skips_empty_articles(mock_page, mock_article, mock_sleep):
    mock_page.return_value = (
        '<html><body><a href="/stories/jane">Jane</a></body></html>'
    )
    mock_article.return_value = ""

    leads = m4._scrape_nonprofit("https://defyventures.org/alumni-stories/")
    assert leads == []


# ---------------------------------------------------------------------------
# _listennotes_search
# ---------------------------------------------------------------------------


def _mock_ln_response(episodes):
    mock = MagicMock()
    mock.json.return_value = {"results": episodes}
    mock.raise_for_status = MagicMock()
    return mock


def _make_episode(
    title="Healing Podcast",
    description="Great story.",
    url="https://listennotes.com/e/abc",
):
    return {
        "title_original": title,
        "description_original": description,
        "listennotes_url": url,
        "podcast": {"title_original": "Healing Show"},
    }


@patch("modules.m4_nonprofits.requests.get")
def test_listennotes_search_returns_leads(mock_get):
    mock_get.return_value = _mock_ln_response([_make_episode()])
    leads = m4._listennotes_search("Joe Dispenza healing story")
    assert len(leads) == 1
    assert leads[0]["Source"] == "listennotes"
    assert leads[0]["Archetype"] == "health"


@patch("modules.m4_nonprofits.requests.get")
def test_listennotes_search_skips_episodes_without_description(mock_get):
    ep = _make_episode()
    ep["description_original"] = ""
    mock_get.return_value = _mock_ln_response([ep])
    leads = m4._listennotes_search("Joe Dispenza healing story")
    assert leads == []


@patch("modules.m4_nonprofits.requests.get")
def test_listennotes_search_http_error_returns_empty(mock_get):
    import requests as req_lib

    mock_get.return_value.raise_for_status.side_effect = req_lib.HTTPError("429")
    leads = m4._listennotes_search("former prisoner entrepreneur")
    assert leads == []


# ---------------------------------------------------------------------------
# discover() — all external I/O mocked
# ---------------------------------------------------------------------------


@patch("modules.m4_nonprofits.time.sleep")
@patch("modules.m4_nonprofits._listennotes_search")
@patch("modules.m4_nonprofits._scrape_nonprofit")
def test_discover_returns_leads(mock_scrape, mock_ln, mock_sleep):
    mock_scrape.return_value = []
    mock_ln.return_value = [
        {
            "Archetype": "health",
            "Source": "listennotes",
            "Source URL": "https://listennotes.com/e/jane",
            "Status": "New",
            "_content": "Story text.",
        }
    ]

    leads = m4.discover()
    assert len(leads) >= 1
    assert leads[0]["Source"] == "listennotes"
    assert "Claude Score" not in leads[0]
    mock_scrape.assert_not_called()


@patch("modules.m4_nonprofits.time.sleep")
@patch("modules.m4_nonprofits._listennotes_search")
@patch("modules.m4_nonprofits._scrape_nonprofit")
def test_discover_deduplicates_urls(mock_scrape, mock_ln, mock_sleep):
    dup_lead = {
        "Archetype": "criminal",
        "Source": "nonprofit",
        "Source URL": "https://defyventures.org/stories/jane",
        "Status": "New",
        "_content": "Story.",
    }
    mock_scrape.return_value = [dup_lead]
    mock_ln.return_value = [dup_lead]

    leads = m4.discover(include_nonprofits=True)
    urls = [lead["Source URL"] for lead in leads]
    assert urls.count("https://defyventures.org/stories/jane") == 1


@patch("modules.m4_nonprofits.time.sleep")
@patch("modules.m4_nonprofits._listennotes_search")
@patch("modules.m4_nonprofits._scrape_nonprofit")
def test_discover_skips_nonprofit_urls_by_default(mock_scrape, mock_ln, mock_sleep):
    mock_scrape.return_value = []
    mock_ln.return_value = []

    m4.discover()

    mock_scrape.assert_not_called()


@patch("modules.m4_nonprofits.time.sleep")
@patch("modules.m4_nonprofits._listennotes_search")
@patch("modules.m4_nonprofits._scrape_nonprofit")
def test_discover_can_include_paused_nonprofit_urls(mock_scrape, mock_ln, mock_sleep):
    mock_scrape.return_value = []
    mock_ln.return_value = []

    m4.discover(include_nonprofits=True)

    assert mock_scrape.call_count == len(NONPROFIT_URLS)


@patch("modules.m4_nonprofits.time.sleep")
@patch("modules.m4_nonprofits._listennotes_search")
@patch("modules.m4_nonprofits._scrape_nonprofit")
def test_discover_searches_all_listennotes_queries(mock_scrape, mock_ln, mock_sleep):
    mock_scrape.return_value = []
    mock_ln.return_value = []

    m4.discover()

    assert mock_ln.call_count == len(LISTENNOTES_QUERIES)
