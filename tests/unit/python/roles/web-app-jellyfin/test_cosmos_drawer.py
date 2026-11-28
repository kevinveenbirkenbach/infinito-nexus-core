from __future__ import annotations

import unittest

from tests.lint.filesystem.test_cosmos_sheets import ROLES, SHEET, sky_colors
from utils.cache.files import read_text

JELLYFIN_SHEET = ROLES / "web-app-jellyfin" / SHEET
DRAWER = ".mainDrawer"
DESIGN_TEXT = "var(--design-text)"
COSMOS_TEXT = "var(--cosmos-text)"
DRAWER_RULE = (
    "{{ COSMOS_SKY_SELECTOR }}[data-design-palette] .mainDrawer {\n"
    "  color: var(--design-text);\n}\n"
)


class TestJellyfinCosmosDrawer(unittest.TestCase):
    def setUp(self) -> None:
        self.sheet = read_text(str(JELLYFIN_SHEET))

    def test_the_sky_turns_the_page_text_to_the_cosmos_text(self) -> None:
        self.assertIn(COSMOS_TEXT, sky_colors(self.sheet, "body"))

    def test_the_drawer_takes_the_design_text_back(self) -> None:
        self.assertEqual(
            sky_colors(self.sheet, DRAWER),
            [DESIGN_TEXT],
            "the navigation drawer sits on --design-surface-2 outside "
            ".mainAnimatedPages and its entries inherit their color, so text "
            "inherited from the sky's --cosmos-text on body is unreadable",
        )

    def test_a_sheet_without_the_drawer_rule_is_caught(self) -> None:
        self.assertIn(DRAWER_RULE, self.sheet)
        stripped = self.sheet.replace(DRAWER_RULE, "")
        self.assertIn(COSMOS_TEXT, sky_colors(stripped, "body"))
        self.assertEqual(sky_colors(stripped, DRAWER), [])


if __name__ == "__main__":
    unittest.main()
