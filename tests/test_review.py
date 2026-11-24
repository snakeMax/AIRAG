"""tools/review.py's hard checks run with the tests, so a broken import, route or text key fails CI."""
import importlib


def test_review_finds_no_errors():
    review = importlib.import_module("tools.review")
    review.errors.clear()
    for check in (review.check_js, review.check_routes, review.check_i18n, review.check_rules):
        check()
    assert review.errors == []
