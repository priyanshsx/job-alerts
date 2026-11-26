#---------------------beginning-of-code------------------------#
#--------------------------------------------------------------#

# File: tests/test_research.py
# Purpose: the research step against a fake company website (no network).
# Run:     python3 tests/test_research.py
#--------------------------------------------------------------#

# Imports libraries
from datetime import date, timedelta
import httpx
from job_alerts.crawler import web
from job_alerts.research import pages, rules
#--------------------------------------------------------------#

TODAY = date.today()
D = lambda days: (TODAY - timedelta(days=days))
MENU = "<nav><p>Home</p><p>Lösungen SAP S/4HANA</p><p>News</p><p>Karriere</p></nav><footer><p>© 2026 Muster GmbH</p></footer>"
SITE = {
    "/robots.txt": ("text/plain", "User-agent: *\nDisallow: /intern/\nSitemap: https://www.muster.de/sitemap.xml"),
    "/": ("text/html", f'<html lang="de"><head><link rel="alternate" type="application/rss+xml" href="/feed"></head>'
                       f'<body>{MENU}<a href="/news/">News</a><a href="/karriere/">Jobs</a></body></html>'),
    "/feed": ("application/rss+xml", f"""<rss><channel>
        <item><title>Muster übernimmt Beispiel AG</title><link>https://www.muster.de/news/uebernahme</link>
        <pubDate>{D(10).strftime('%a, %d %b %Y')} 08:00:00 +0000</pubDate><description>Die Übernahme stärkt ...</description></item>
        <item><title>Sommerfest 2025</title><link>https://www.muster.de/news/sommerfest</link>
        <pubDate>{D(400).strftime('%a, %d %b %Y')} 08:00:00 +0000</pubDate></item></channel></rss>"""),
    "/sitemap.xml": ("application/xml", f"""<urlset>
        <url><loc>https://www.muster.de/news/werk-brno</loc><lastmod>{D(40).isoformat()}</lastmod></url>
        <url><loc>https://www.muster.de/produkte/pumpe-x</loc><lastmod>{D(2).isoformat()}</lastmod></url>
        <url><loc>https://www.muster.de/karriere/sap-berater</loc><lastmod>{D(1).isoformat()}</lastmod></url>
        </urlset>"""),
    "/news/": ("text/html", f'<html lang="de"><body>{MENU}<a href="/news/uebernahme">a</a><a href="/news/sap-golive">b</a></body></html>'),
    "/news/uebernahme": ("text/html", f'<html lang="de"><head><meta property="article:published_time" content="{D(10).isoformat()}"></head>'
                                      f'<body>{MENU}<h1>Muster übernimmt Beispiel AG</h1><p>Mit der Übernahme wächst die Gruppe auf 900 Mitarbeitende. '
                                      f'Die Integration ist für 2027 geplant.</p></body></html>'),
    "/news/werk-brno": ("text/html", f'<html lang="de"><body>{MENU}<h1>Spatenstich in Brno</h1><p>{D(40).strftime("%d.%m.%Y")} '
                                     f'Heute war der Spatenstich für unser neues Werk in Tschechien.</p></body></html>'),
    "/news/sap-golive": ("text/html", f'<html lang="en"><body>{MENU}<h1>We went live</h1><time datetime="{D(5).isoformat()}"></time>'
                                      f'<p>After 18 months our S/4HANA go-live happened on time. Master data was cleaned in advance.</p></body></html>'),
    "/produkte/pumpe-x": ("text/html", f'<html lang="de"><body>{MENU}<h1>Pumpe X</h1><p>Technische Daten.</p></body></html>'),
}

def handler(request: httpx.Request) -> httpx.Response:
    kind, body = SITE.get(request.url.path, (None, None))
    if body is None:
        return httpx.Response(404)
    return httpx.Response(200, headers={"content-type": kind}, text=body)
#--------------------------------------------------------------#

def main() -> None:
    web._client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)
    web.DELAY_SECONDS = 0
    result = pages.read_site("https://www.muster.de/", D(90), max_pages=15)
    by_url = {p["url"].rsplit("/", 1)[-1]: p for p in result["pages"]}
    print(result["status"], {k: (v["published_at"], v["date_source"], v["lang"]) for k, v in by_url.items()})
    assert result["status"] == "ok"
    assert set(by_url) == {"uebernahme", "werk-brno", "sap-golive"}, by_url.keys()     # old, product, job pages left out
    assert by_url["werk-brno"]["published_at"] == D(40).isoformat()
    assert by_url["sap-golive"]["lang"] == "en"
    assert "S/4HANA" not in by_url["uebernahme"]["text"], "menu line should be removed"

    import yaml
    cfg = yaml.safe_load(open("config/clients/vizcorn/config.yaml"))["research"]
    events = rules.compile_events(cfg["events"])
    found = {k: [m["event"] for m in rules.match_page(p, events, cfg["half_life_days"])] for k, p in by_url.items()}
    print(found)
    assert found["uebernahme"][0] == "acquisition"
    assert "new_site" in found["werk-brno"]
    assert found["sap-golive"][:2] == ["s4hana", "erp_golive"] or set(found["sap-golive"][:2]) == {"s4hana", "erp_golive"}
    m = rules.match_page(by_url["sap-golive"], events, 30)[0]
    print(m["snippet"])
    assert rules._pattern("raises $").search("Acme raises $5m")
    assert rules._pattern("inaugurat*").search("The plant was inaugurated today")
    assert not rules._pattern("fusion").search("Kernfusionsreaktor")
    assert pages.text_date("Veröffentlicht am 3. November 2026") == date(2026, 11, 3)
    assert pages.text_date("Published November 3, 2026") == date(2026, 11, 3)
    assert pages.text_date("Publicado el 3 de noviembre de 2026") == date(2026, 11, 3)
    print("all research tests passed")


if __name__ == "__main__":
    main()
#--------------------------------------------------------------#
#---------------------end-of-code------------------------------#
