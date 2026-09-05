"""JD-enrichment parsing tests (no network — exercise the extractors directly)."""
from radar import enrich


def test_jsonld_jobposting_extraction():
    html = """
    <html><head>
    <script type="application/ld+json">
    {"@context":"https://schema.org","@type":"JobPosting",
     "title":"SWE Intern",
     "description":"<p>Build backend services in Python and PostgreSQL. Deploy on AWS.</p>"}
    </script>
    </head></html>
    """
    out = enrich._jsonld_jobposting(html)
    assert out and "Python" in out and "<p>" not in out  # HTML stripped


def test_jsonld_handles_graph_nesting():
    html = """
    <script type="application/ld+json">
    {"@graph":[{"@type":"Organization","name":"Acme"},
               {"@type":"JobPosting","description":"Kubernetes and Go role."}]}
    </script>
    """
    out = enrich._jsonld_jobposting(html)
    assert out == "Kubernetes and Go role."


def test_jsonld_returns_none_when_absent():
    assert enrich._jsonld_jobposting("<html><body>no structured data</body></html>") is None


def test_url_regexes():
    assert enrich.RE_GREENHOUSE.search("https://job-boards.greenhouse.io/morsecorp/jobs/7968338003")
    assert enrich.RE_LEVER.search("https://jobs.lever.co/flyhomes/abc-123")
    assert enrich.RE_ASHBY.search(
        "https://jobs.ashbyhq.com/rivet/4e02461a-9f6c-4d3c-a511-6d54f31999bc/application"
    )
    # a non-ATS URL matches none of the board patterns
    url = "https://www.amazon.jobs/en/jobs/10517567/software-development-engineer-intern"
    assert not enrich.RE_GREENHOUSE.search(url)
    assert not enrich.RE_ASHBY.search(url)


def test_strip_collapses_whitespace_and_tags():
    assert enrich._strip("<p>hello&nbsp;&amp;   world</p>") == "hello & world"
