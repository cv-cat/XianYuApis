import hashlib
import json
import unittest
from unittest.mock import Mock, patch

import requests

from item_analytics import API, AnalyticsError, ItemAnalytics


def body(ids, total, **metrics):
    return {
        "data": {"list": [{"itmId": i, **metrics} for i in ids], "total": total},
        "extendInfo": {"realDateRange": ["20260101", "20260107"]},
    }


class ItemAnalyticsTests(unittest.TestCase):
    def setUp(self):
        self.session = requests.Session()
        self.session.cookies.set("_m_h5_tk", "fake-token_999", domain=".goofish.com")
        self.client = ItemAnalytics(session=self.session)

    def response(self, payload):
        response = Mock(is_redirect=False)
        response.json.return_value = payload
        return response

    def test_signature_matches_exact_unicode_form_and_reuses_session(self):
        response = self.response({"ret": ["SUCCESS::调用成功"],
                                  "data": {"code": "success", **body(["example-1"], 1)}})
        with patch.object(self.session, "post", return_value=response) as post:
            with patch("item_analytics.time.time", return_value=123.456):
                result = self.client.item_page(keyword="示例", order_by="showPv", order="desc")
        self.assertIs(self.client.session, self.session)
        args, kwargs = post.call_args
        data = kwargs["data"]["data"]
        self.assertIn("示例", data)
        self.assertEqual(kwargs["params"]["t"], "123456")
        expected = hashlib.md5(f"fake-token&123456&34839810&{data}".encode()).hexdigest()
        self.assertEqual(kwargs["params"]["sign"], expected)
        self.assertEqual(args[0], f"https://h5api.m.goofish.com/h5/{API}/1.0/")
        self.assertFalse(kwargs["allow_redirects"])
        self.assertEqual(json.loads(data)["orderBy"], "showPv")
        self.assertEqual(result["data"]["total"], 1)

    def test_missing_token_stops_before_network(self):
        self.session.cookies.clear()
        with patch.object(self.session, "post") as post:
            with self.assertRaises(AnalyticsError):
                self.client.item_page()
        post.assert_not_called()

    def test_failed_mtop_or_business_status_is_not_success(self):
        for payload in [
            {"ret": ["FAIL_SYS_SESSION_EXPIRED::expired"], "data": {}},
            {"ret": ["SUCCESS::调用成功"], "data": {"code": "denied"}},
        ]:
            with self.subTest(payload=payload):
                with patch.object(self.session, "post", return_value=self.response(payload)) as post:
                    with self.assertRaises(AnalyticsError):
                        self.client.item_page()
                    self.assertEqual(post.call_count, 1)

    def test_redirect_and_non_json_stop(self):
        redirect = Mock(is_redirect=True)
        invalid = Mock(is_redirect=False)
        invalid.json.side_effect = ValueError("not json")
        for response in [redirect, invalid]:
            with patch.object(self.session, "post", return_value=response):
                with self.assertRaises(AnalyticsError):
                    self.client.item_page()

    def test_transport_error_does_not_disclose_signed_url(self):
        with patch.object(self.session, "post", side_effect=requests.ConnectionError("sign=private")):
            with self.assertRaises(AnalyticsError) as error:
                self.client.item_page()
        self.assertNotIn("private", str(error.exception))

    def test_custom_range_validation_and_serialization(self):
        with patch.object(self.client, "_request", return_value=body([], 0)) as request:
            self.client.item_page(date_type="customDate", date_range="20260101|20260107")
            self.assertEqual(request.call_args.args[1]["dateRange"], "20260101|20260107")
            for date_range in ["20260230|20260301", "20260107|20260101", "2026-01-01|20260107"]:
                with self.assertRaises(ValueError):
                    self.client.item_page(date_type="customDate", date_range=date_range)

    def test_collect_deduplicates_overlap_and_preserves_zero(self):
        with patch.object(self.client, "item_page", side_effect=[
            body(["example-1", "example-2"], 3, showPv=0),
            body(["example-2", "example-3"], 3, showPv=0),
        ]):
            result = self.client.collect(interval=0)
        self.assertTrue(result["complete"])
        self.assertEqual(result["count"], 3)
        self.assertEqual(result["items"][0]["showPv"], 0)
        self.assertEqual(result["pages"][0]["extendInfo"]["realDateRange"], ["20260101", "20260107"])

    def test_repeated_or_empty_page_preserves_partial_result(self):
        for second in [body(["example-1"], 2), body([], 2)]:
            with self.subTest(second=second):
                with patch.object(self.client, "item_page", side_effect=[body(["example-1"], 2), second]):
                    result = self.client.collect(interval=0)
                self.assertFalse(result["complete"])
                self.assertEqual(result["count"], 1)
                self.assertEqual(result["stop_reason"], "empty_or_repeated_page")

    def test_page_limit_is_reported_as_incomplete(self):
        with patch.object(self.client, "item_page", return_value=body(["example-1"], 2)):
            result = self.client.collect(max_pages=1, interval=0)
        self.assertFalse(result["complete"])
        self.assertEqual(result["stop_reason"], "max_pages")


if __name__ == "__main__":
    unittest.main()
