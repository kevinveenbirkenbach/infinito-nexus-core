"""Contract of ``lookup('network_siblings')``: every logical domain renders
once per network its app is served on, and exactly once overall."""

from __future__ import annotations

import unittest

from plugins.lookup.network_siblings import served_siblings

ONION = "abc123def456ghij789klmno000pqrstuvwx111yz222abc333def444gh.onion"
PRIMARY = "infinito.test"


class TestServedSiblings(unittest.TestCase):
    def test_multi_app_renders_both_networks_from_the_canonical_domain(self) -> None:
        domains = {"web-app-x": ["x.infinito.test", f"x.{ONION}"]}
        self.assertEqual(
            served_siblings("x.infinito.test", domains, PRIMARY, ONION),
            ["x.infinito.test", f"x.{ONION}"],
        )

    def test_multi_app_skips_the_non_canonical_sibling(self) -> None:
        domains = {"web-app-x": ["x.infinito.test", f"x.{ONION}"]}
        self.assertEqual(served_siblings(f"x.{ONION}", domains, PRIMARY, ONION), [])

    def test_tor_only_app_maps_a_raw_clearnet_domain_to_its_onion(self) -> None:
        domains = {"web-app-x": [f"x.{ONION}"]}
        self.assertEqual(
            served_siblings("x.infinito.test", domains, PRIMARY, ONION), [f"x.{ONION}"]
        )

    def test_clearnet_only_app_renders_one_vhost(self) -> None:
        domains = {"web-app-x": ["x.infinito.test"]}
        self.assertEqual(
            served_siblings("x.infinito.test", domains, PRIMARY, ONION),
            ["x.infinito.test"],
        )

    def test_named_canonicals_fan_out_per_key(self) -> None:
        domains = {
            "web-app-x": {
                "api": "api.infinito.test",
                "web": "web.infinito.test",
                "api_onion": f"api.{ONION}",
                "web_onion": f"web.{ONION}",
            }
        }
        self.assertEqual(
            served_siblings("web.infinito.test", domains, PRIMARY, ONION),
            ["web.infinito.test", f"web.{ONION}"],
        )

    def test_unknown_domain_renders_as_given(self) -> None:
        self.assertEqual(
            served_siblings("elsewhere.example", {}, PRIMARY, ONION),
            ["elsewhere.example"],
        )

    def test_node_without_tor_renders_as_given(self) -> None:
        domains = {"web-app-x": ["x.infinito.test"]}
        self.assertEqual(
            served_siblings("x.infinito.test", domains, PRIMARY, ""),
            ["x.infinito.test"],
        )


if __name__ == "__main__":
    unittest.main()
