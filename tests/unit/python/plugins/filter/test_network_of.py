import unittest

from plugins.filter.network_of import FilterModule

ONION = "abc123def456ghij789klmno000pqrstuvwx111yz222abc333def444gh.onion"


class TestNetworkFilters(unittest.TestCase):
    def setUp(self):
        self.filters = FilterModule().filters()

    def test_network_of_is_the_registry_lookup(self):
        self.assertEqual(self.filters["network_of"]("x.abc.onion"), "tor")
        self.assertEqual(self.filters["network_of"]("x.infinito.test"), "clearnet")

    def test_network_sibling_translates_the_primary(self):
        self.assertEqual(
            self.filters["network_sibling"](
                "infinito.test", "tor", "infinito.test", ONION
            ),
            ONION,
        )

    def test_network_suffix_comes_from_the_registry(self):
        self.assertEqual(self.filters["network_suffix"]("tor"), ".onion")
        self.assertEqual(self.filters["network_suffix"]("clearnet"), "")

    def test_network_suffixes_maps_only_networks_with_a_suffix(self):
        self.assertEqual(
            self.filters["network_suffixes"](["clearnet", "tor"]), {"tor": ".onion"}
        )
        self.assertEqual(self.filters["network_suffixes"](["clearnet"]), {})

    def test_in_network_keeps_the_domains_of_one_network(self):
        domains = ["a.infinito.test", f"a.{ONION}", "b.infinito.test"]
        self.assertEqual(
            self.filters["in_network"](domains, "clearnet"),
            ["a.infinito.test", "b.infinito.test"],
        )
        self.assertEqual(self.filters["in_network"](domains, "tor"), [f"a.{ONION}"])

    def test_network_sibling_is_empty_without_a_node(self):
        self.assertEqual(
            self.filters["network_sibling"](
                "infinito.test", "tor", "infinito.test", ""
            ),
            "",
        )


if __name__ == "__main__":
    unittest.main()
