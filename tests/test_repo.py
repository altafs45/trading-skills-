"""Repo rules: the twelve skills, frontmatter, SKILL.md size, manifests, no order endpoints, stdlib only, fake fixtures."""

import ast
import json
import os
import re
import sys
import unittest

from _load import ROOT

SKILLS = sorted(["trader-scanner", "trader-news", "trader-entry", "trader-exit", "trader-timemachine", "trader-budget",
                 "trader-risk", "trader-ticket", "trader-alerts", "trader-analyst", "trader-track", "trader-analyze"])
LIB = {"nse_common", "nse_parsers", "nse_research", "indicators", "breakout", "chart", "kite_login", "_load"}


def py_files():
    for base, dirs, files in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d not in (".git", "__pycache__")]
        for f in files:
            if f.endswith(".py"):
                yield os.path.join(base, f)


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


class Repo(unittest.TestCase):
    def test_twelve_skills(self):
        found = sorted(d for d in os.listdir(ROOT) if os.path.isfile(os.path.join(ROOT, d, "SKILL.md")))
        self.assertEqual(found, SKILLS)

    def test_skill_md(self):
        for s in SKILLS:
            text = read(os.path.join(ROOT, s, "SKILL.md"))
            m = re.match(r"^---\nname: (\S+)\ndescription: >-\n(.*?)\n---\n", text, re.S)
            self.assertTrue(m, s)
            self.assertEqual(m.group(1), s)
            self.assertGreater(len(m.group(2)), 300, s)
            self.assertIn('"', m.group(2), s + ": trigger phrases")
            self.assertLess(len(text.splitlines()), 120, s)
            low = text.lower()
            for must in ("not financial advice", "never place", "summary"):
                self.assertIn(must, low, "%s: %s" % (s, must))

    def test_manifests(self):
        p = json.loads(read(os.path.join(ROOT, ".claude-plugin", "plugin.json")))
        m = json.loads(read(os.path.join(ROOT, ".claude-plugin", "marketplace.json")))
        self.assertEqual(p["name"], "nse-day-trader")
        self.assertEqual(p["skills"], "./")
        self.assertEqual(m["plugins"][0]["name"], p["name"])

    def test_no_order_endpoints_anywhere(self):
        bad = re.compile(r"placeOrder|modifyOrder|cancelOrder|place_order|modify_order|cancel_order|kite\.trade/orders|/orders/(regular|amo|co|iceberg|auction)|gtt/triggers|place_stock_order", re.I)
        for p in py_files():
            if p.endswith("test_repo.py"):
                continue
            self.assertIsNone(bad.search(read(p)), p)

    def test_stdlib_only(self):
        std = set(getattr(sys, "stdlib_module_names", ())) or None
        for p in py_files():
            tree = ast.parse(read(p))
            for node in ast.walk(tree):
                names = [a.name for a in node.names] if isinstance(node, ast.Import) else \
                    [node.module] if isinstance(node, ast.ImportFrom) and node.module else []
                for n in names:
                    top = n.split(".")[0]
                    if top in LIB or top.startswith("test_"):
                        continue
                    if std is not None:
                        self.assertIn(top, std, "%s imports %s" % (p, n))

    def test_credentials_never_printed(self):
        for p in py_files():
            for line in read(p).splitlines():
                if "print(" in line:
                    self.assertIsNone(re.search(r"\b(api_secret|access_token|request_token|api_key)\b(?!\s*=)", line), "%s: %s" % (p, line.strip()))

    def test_fixtures_are_labelled_fake(self):
        fx = os.path.join(ROOT, "tests", "fixtures")
        self.assertIn("SYNTHETIC", read(os.path.join(fx, "README.md")))
        for f in os.listdir(fx):
            if f != "README.md":
                self.assertTrue(f.startswith("fake_"), f)
                self.assertRegex(read(os.path.join(fx, f)), r"FAKE|SYNTHETIC|Fake", f)


if __name__ == "__main__":
    unittest.main()
