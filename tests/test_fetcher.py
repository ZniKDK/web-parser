import pytest
import requests

from web_parser.fetcher import BlockedByRobots, FetchError, Fetcher

URL = "https://shop.example/catalog"


class FakeResponse:
    def __init__(self, status=200, text="<html>ok</html>", encoding="utf-8"):
        self.status_code = status
        self.text = text
        self.encoding = encoding
        self.apparent_encoding = "utf-8"


class FakeSession:
    """Возвращает ответы по очереди; robots.txt — отдельно."""

    def __init__(self, responses, robots=None):
        self.responses = list(responses)
        self.robots = robots
        self.headers = {}
        self.calls = []

    def get(self, url, timeout=None):
        if url.endswith("/robots.txt"):
            return self.robots or FakeResponse(404, "")
        self.calls.append(url)
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def make(responses, robots=None, **kwargs):
    session = FakeSession(responses, robots)
    fetcher = Fetcher(delay=0, backoff=0, session=session, **kwargs)
    return fetcher, session


def test_ok():
    fetcher, session = make([FakeResponse(text="hello")])
    assert fetcher.get(URL) == "hello"
    assert session.headers["User-Agent"].startswith("Mozilla/5.0")


def test_retries_on_server_error_and_network_failure():
    fetcher, session = make([
        FakeResponse(503),
        requests.ConnectionError("обрыв"),
        FakeResponse(text="наконец"),
    ])
    assert fetcher.get(URL) == "наконец"
    assert len(session.calls) == 3
    assert fetcher.stats["retries"] == 2


def test_gives_up_after_retries():
    fetcher, session = make([FakeResponse(500)] * 3, retries=2)
    with pytest.raises(FetchError, match="HTTP 500"):
        fetcher.get(URL)
    assert len(session.calls) == 3


def test_not_found_is_not_retried():
    fetcher, session = make([FakeResponse(404), FakeResponse()])
    with pytest.raises(FetchError, match="404"):
        fetcher.get(URL)
    assert len(session.calls) == 1


def test_wrong_latin1_encoding_fixed():
    response = FakeResponse(encoding="ISO-8859-1")
    fetcher, _ = make([response])
    fetcher.get(URL)
    assert response.encoding == "utf-8"


def test_robots_disallow():
    robots = FakeResponse(text="User-agent: *\nDisallow: /catalog")
    fetcher, session = make([FakeResponse()], robots=robots)
    with pytest.raises(BlockedByRobots):
        fetcher.get(URL)
    assert session.calls == []


def test_robots_can_be_ignored():
    robots = FakeResponse(text="User-agent: *\nDisallow: /")
    fetcher, _ = make([FakeResponse(text="ok")], robots=robots, respect_robots=False)
    assert fetcher.get(URL) == "ok"


def test_cache_avoids_second_request(tmp_path):
    fetcher, session = make([FakeResponse(text="страница")], cache_dir=tmp_path)
    assert fetcher.get(URL) == "страница"
    assert fetcher.get(URL) == "страница"
    assert len(session.calls) == 1
    assert fetcher.stats["cache_hits"] == 1


def test_rate_limit(monkeypatch):
    sleeps = []
    monkeypatch.setattr("web_parser.fetcher.time.sleep", sleeps.append)
    session = FakeSession([FakeResponse(), FakeResponse()])
    fetcher = Fetcher(delay=5, session=session)
    fetcher.get(URL)
    fetcher.get(URL + "/2")
    # Второй запрос сразу за первым — фетчер должен подождать почти всю паузу
    assert sleeps and sleeps[-1] > 4
