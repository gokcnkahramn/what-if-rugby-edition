"""Generic MediaWiki `{|class="wikitable"|}` table-parsing helpers - real
wikitext cell/row cleanup that doesn't belong to any one squad source.
Originally written inside `historical_rwc.py` (for the RWC statistics
tables) and used as-is by `invitational_squads.py` (for the Lions tour
squad table) - hoisted here so a module named after one specific squad
source isn't the de facto owner of utilities every wikitable parser in
this project needs.
"""

from __future__ import annotations

import re
from typing import List


def clean_wiki_cell(text: str) -> str:
    """Strips the common real wikitext markup found inside a table cell
    (refs, `{{template|params}}`, `[[wikilink|display]]`, bold/italic) down
    to plain display text - e.g. `{{Ru|FRA}}` -> `FRA`, `[[Thierry
    Lacroix]]` -> `Thierry Lacroix`, `'''112'''` -> `112`."""
    text = re.sub(r"<ref[^>]*>.*?</ref>", "", text, flags=re.S)
    text = re.sub(r"<ref[^>]*/?>", "", text)
    # {{tooltip|Conv|Conversions}} / {{Ru|FRA}} -> last "|"-separated param;
    # {{shy}} (soft hyphen, no params) -> drop entirely.
    text = re.sub(r"\{\{[^{}]*\|([^{}]*)\}\}", r"\1", text)
    text = re.sub(r"\{\{[^{}]*\}\}", "", text)
    text = re.sub(r"\[\[[^\]|]*\|([^\]]*)\]\]", r"\1", text)
    text = re.sub(r"\[\[([^\]]*)\]\]", r"\1", text)
    text = text.replace("'''", "").replace("''", "")
    return text.strip()


def strip_wiki_cell_attrs(cell: str) -> str:
    """A real wikitext cell is often `align="left"|<content>` or
    `width=40|<content>` (style attributes before the actual value,
    separated by the first real `|`) - strips that prefix when present,
    leaving the raw `<content>`."""
    cell = cell.strip()
    if "|" in cell and "[[" not in cell.split("|", 1)[0]:
        prefix, rest = cell.split("|", 1)
        if re.match(r'^[A-Za-z0-9"=:;#\-\s]*$', prefix):
            return rest.strip()
    return cell


def split_wiki_row_cells(row_lines: List[str]) -> List[str]:
    """A real wikitext table row can span several raw lines (one cell per
    line) AND/OR pack several cells onto one line with `||` (data cells)
    or `!!` (header cells) separators - confirmed live on both the 1995
    and 2003 RWC statistics pages, which even mix a `|`-prefixed cell and
    a `!`-prefixed cell on the SAME line (e.g. `|5||! scope=row
    style="background:#ccc"|'''7'''||0||0||0||35`, marking the sorted
    column). This normalizes all of those real separator forms to one
    delimiter before splitting, so the drift doesn't need a special case."""
    joined = "\n".join(row_lines)
    joined = re.sub(r"\n\s*[|!]", "\x01", joined)
    joined = re.sub(r"\|\s*!|\|\||!!", "\x01", joined)
    joined = joined.lstrip("|!").strip()
    raw_cells = [c for c in joined.split("\x01")]
    return [clean_wiki_cell(strip_wiki_cell_attrs(c)) for c in raw_cells if c.strip() != ""]
