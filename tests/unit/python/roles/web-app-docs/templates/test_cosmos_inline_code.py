from __future__ import annotations

import unittest

from tests.lint.filesystem.test_cosmos_sheets import render, rules, selectors
from utils.cache import PROJECT_ROOT
from utils.cache.files import read_text

SHEET = PROJECT_ROOT / "roles" / "web-app-docs" / "templates" / "cosmos.css.j2"
INLINE_CODE = "code:not(pre code)"
CODE_BLOCK = "div.highlight pre"
DESIGN_TEXT = "var(--design-text)"
DESIGN_SURFACE = "var(--design-surface-1)"
COSMOS_TEXT = "var(--cosmos-text)"
CODE_BLOCK_SURFACE = (
    "{{ COSMOS_SKY_SELECTOR }} div.highlight pre {\n"
    "  background-color: var(--design-surface-1);\n"
)
CODE_BLOCK_BARE = "{{ COSMOS_SKY_SELECTOR }} div.highlight pre {\n"


def sky_values(text: str, subject: str, prop: str) -> list[str]:
    """
    Args:
        text: a cosmos sheet template.
        subject: the trailing selector part to match.
        prop: the declared property to collect.

    Returns:
        The ``prop`` value of every rule that applies under the sky outside
        the legible-top band and selects ``subject``.
    """
    sky, top = selectors()
    return [
        declared[prop]
        for chosen, declared in rules(render(text, sky, top))
        for selector in chosen
        if prop in declared
        and selector.startswith(sky)
        and not selector.startswith(top)
        and selector.endswith(subject)
    ]


class TestDocsCosmosInlineCode(unittest.TestCase):
    def setUp(self) -> None:
        self.sheet = read_text(str(SHEET))

    def test_the_sky_turns_the_page_text_to_the_cosmos_text(self) -> None:
        self.assertIn(COSMOS_TEXT, sky_values(self.sheet, "body", "color"))

    def test_inline_code_keeps_the_design_text_on_its_own_surface(self) -> None:
        self.assertEqual(sky_values(self.sheet, INLINE_CODE, "color"), [DESIGN_TEXT])
        self.assertEqual(sky_values(self.sheet, INLINE_CODE, "background-color"), [])

    def test_code_blocks_keep_the_design_text_on_their_own_surface(self) -> None:
        self.assertEqual(sky_values(self.sheet, CODE_BLOCK, "color"), [DESIGN_TEXT])
        self.assertEqual(
            sky_values(self.sheet, CODE_BLOCK, "background-color"),
            [DESIGN_SURFACE],
            "the theme clears div.highlight and pre carries no surface, so "
            "--design-text would sit on the bare sky",
        )

    def test_a_code_block_without_its_surface_is_caught(self) -> None:
        self.assertIn(CODE_BLOCK_SURFACE, self.sheet)
        stripped = self.sheet.replace(CODE_BLOCK_SURFACE, CODE_BLOCK_BARE)
        self.assertEqual(sky_values(stripped, CODE_BLOCK, "color"), [DESIGN_TEXT])
        self.assertEqual(sky_values(stripped, CODE_BLOCK, "background-color"), [])


if __name__ == "__main__":
    unittest.main()
