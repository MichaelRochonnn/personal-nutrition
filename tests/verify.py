"""Offline regression tests. All people, menus and prices in these tests are synthetic."""
import json
import math
import re
import sys
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import graph
import kitchen
import review_menu
import read_harvard


def input_menu():
    verified = {"allergies_and_cross_contact": "2026-11-12", "other_exclusions": "2026-11-12"}
    members = [
        {"member_id": "A", "current_stage": "计划妊娠", "allergies_and_cross_contact": ["牛奶蛋白过敏"],
         "other_exclusions": [], "confirmed_at": verified.copy()},
        {"member_id": "B", "current_stage": "伴侣备孕", "allergies_and_cross_contact": ["大豆过敏"],
         "other_exclusions": [], "confirmed_at": verified.copy()},
    ]
    dish = {"name": "共用底菜", "eaters": ["A", "B"], "stage_sensitive": True,
            "planned_stage": {"A": "计划妊娠", "B": "伴侣备孕"}, "kitchen_checked_for": ["A", "B"],
            "all_components_included": True, "components": [
                {"name": "豆腐", "contains": ["大豆", "水", "凝固剂"], "cross_contact": [],
                 "verified_for": ["牛奶蛋白", "大豆过敏"], "basis": "虚构现场核验，本例已查配料和生产条件"}]}
    return {"as_of": "2026-11-12", "members": members, "dishes": [dish]}


class NutritionChecks(unittest.TestCase):
    def test_graph_integrity_and_original_locators(self):
        graph.check()
        claims = graph.read_claims()
        cn_pages = graph.rows("cn-pages.jsonl")
        ada_pages = graph.rows("ada-pages.jsonl")
        sources = graph.read_sources()
        for pages, source, refs in [(cn_pages, "CN", "claim_range_matches"), (ada_pages, "ADA", "claims")]:
            self.assertEqual([p["pdf_page"] for p in pages], list(range(1, sources[source]["pages"] + 1)))
            positions = {i for page in pages for i in page[refs]}
            self.assertEqual(positions, {k for k, c in claims.items() if c["source"] == source})
        spine = {s["spine"]: s for s in graph.rows("harvard-spine.jsonl")}
        for key in [k for k,c in claims.items() if c["source"] == "HAR"] + [r["id"] for r in graph.rows("harvard-recipes.jsonl")]:
            member, start, end = read_harvard.paragraphs_for_id(key)
            self.assertTrue(1 <= start <= end <= spine[member]["p_last"])
        for r in graph.rows("cn-visual-index.jsonl"):
            self.assertTrue(1 <= r["pdf_start"] <= r["pdf_end"] <= len(cn_pages))
            self.assertFalse(set(r["used_by"]) - claims.keys())

    def test_workweek_budget_and_shop(self):
        recipes = ["R%02d" % n for n in range(1, 8)]
        self.assertTrue(all(kitchen.card(r)["minutes"] <= 20 for r in recipes))
        shop = kitchen.shop(recipes)
        rates = json.loads((ROOT / "tests/fixture-prices.json").read_text())["prices"]
        def money(i):
            rate = rates[i["id"]]
            return i["amount"] * rate["price"] / rate["per"]
        planned = sum(money(i) for r in recipes for i in kitchen.card(r)["ingredients"])
        total = sum(money(i) for i in shop["items"])
        self.assertAlmostEqual(total, planned)
        self.assertLess(total, 125)  # Fictional net-ingredient ceiling for seven dinners only.
        self.assertAlmostEqual(sum(money(i) for i in kitchen.shop(recipes, 2)["items"]), 2 * total)
        # The 21-meal field trial includes all three meals per day and a package allowance.
        field = (ROOT / "tests/field-cases.md").read_text()
        days = re.findall(r"\|(\d+)＋(\d+)＝(\d+)\|(\d+)＋(\d+)＋(\d+)＝(\d+)\|", field)
        self.assertEqual(len(days), 7)
        food = 0
        for row in days:
            active, waiting, duration, b, l, d, daily = map(int, row)
            self.assertEqual(active + waiting, duration)
            self.assertLessEqual(duration, 20)
            self.assertEqual(b + l + d, daily)
            food += daily
        self.assertEqual(food + 7 * 3 + 12 + 10, 370)

    def test_travel_without_kitchen(self):
        ids = {c["id"] for c in graph.search(["无厨房"], for_plan=True)}
        self.assertIn("APP-001", ids)
        cards = [kitchen.card(r) for r in ["R09", "R11", "R12", "R13"]]
        self.assertTrue(all(r["mode"] in {"点餐", "即买即食"} for r in cards))
        self.assertTrue(all("锅" not in r["equipment"] for r in cards))
        field = (ROOT / "tests/field-cases.md").read_text().split("## 2　")[1].split("## 3　")[0]
        totals = [tuple(map(int, t)) for t in re.findall(r"(\d+)＋(\d+)＝(\d+)元", field)]
        self.assertEqual(len(totals), 5)
        self.assertTrue(all(a + b == c and c <= 60 for a,b,c in totals))
        self.assertEqual(sum(c for a,b,c in totals), 254)

    def test_household_and_allergen_names(self):
        data = input_menu()
        a,b = review_menu.review(data)
        self.assertEqual(a["result"], "已通过所列条件检查")
        self.assertEqual(b["result"], "排除")
        data["dishes"][0]["components"][0].update(name="无乳糖牛奶", contains=["乳清"])
        a,b = review_menu.review(data)
        self.assertEqual(a["result"], "排除")
        self.assertEqual(b["result"], "已通过所列条件检查")
        self.assertEqual(review_menu.canonical(["soy allergy", "大豆蛋白过敏"]), {"大豆"})
        self.assertIn("计划妊娠", graph.show("EXT-009")["claim"]["population"])

    def test_stage_or_profile_changes(self):
        data = input_menu()
        data["members"][0]["current_stage"] = "孕早期"
        self.assertEqual(review_menu.review(data)[0]["result"], "待核")
        data["members"][0].update(current_stage=None, allergies_and_cross_contact=None, confirmed_at={})
        self.assertEqual(review_menu.review(data)[0]["result"], "待核")
        data = input_menu()
        data["members"][0]["confirmed_at"]["allergies_and_cross_contact"] = "2024-11-12"
        self.assertEqual(review_menu.review(data)[0]["result"], "待核")
        data["members"][0]["reconfirmed_for_this_plan"] = ["allergies_and_cross_contact"]
        self.assertEqual(review_menu.review(data)[0]["result"], "已通过所列条件检查")

    def test_conflicts_and_claim_quality(self):
        self.assertTrue({"HAR-017","CN-009","EXT-003"} <= set(graph.show("C01")["claims"]))
        self.assertIn("C04", {d["id"] for d in graph.show("HAR-016")["discussions"]})
        for key in ["HAR-016","HAR-035","ADA-037","ADA-042","CN-037","CN-044"]:
            self.assertTrue(graph.show(key)["historical_or_review_only"])
        self.assertIn("EXT-031", {c["id"] for c in graph.search(["milk allergy"], for_plan=True)})
        self.assertFalse({c["id"] for c in graph.search([], for_plan=True)} & {"HAR-020","HAR-021","ADA-042"})
        self.assertIn("证据不足", graph.show("EXT-013")["claim"]["relation"])
        self.assertNotEqual(graph.show("EXT-014")["claim"]["relation"], graph.show("EXT-015")["claim"]["relation"])

    def test_substitution_rechecks_whole_dish(self):
        data = input_menu()
        part = data["dishes"][0]["components"][0]
        part.update(name="鸡肉", contains=["鸡肉"], cross_contact=["牛奶"])
        a,b = review_menu.review(data)
        self.assertEqual(a["result"], "排除")
        self.assertEqual(b["result"], "已通过所列条件检查")
        part.update(cross_contact=None, basis=None, verified_for=[])
        self.assertEqual(review_menu.review(data)[0]["result"], "待核")
        part.update(contains=None, cross_contact=[], basis="测试", verified_for=["大豆"])
        self.assertEqual(review_menu.review(data)[1]["result"], "待核")

    def test_missing_data_and_measurement(self):
        example = json.loads((ROOT / "assets/nutrition-input.json").read_text())
        result = kitchen.nutrients(example)["totals"]
        self.assertEqual(result["钠"]["meal"], 0)
        self.assertIsNone(result["维生素C"]["meal"])
        self.assertEqual(result["蛋白质"]["meal"], 3)
        for category in ["oil", "condiment", "drink", "salt"]:
            candidate = deepcopy(example)
            del candidate["review"][category]
            row = kitchen.nutrients(candidate)["totals"]["蛋白质"]
            self.assertIsNone(row["meal"])
            self.assertEqual(row["known_subtotal"], 3)
        for changes in [{"unit":"mL"}, {"state":"熟可食"}, {"amount":-1}, {"edible":False}, {"amount":math.nan}]:
            candidate = deepcopy(example)
            candidate["items"][0]["portion"].update(changes)
            with self.assertRaises(ValueError):
                kitchen.nutrients(candidate)
        candidate = deepcopy(example)
        candidate["items"][0]["basis"]["values"]["钠"]["unit"] = "g"
        with self.assertRaises(ValueError):
            kitchen.nutrients(candidate)

    def test_withdrawn_basis_is_not_used(self):
        claims = graph.read_claims()
        # Simulate a replacement being appended before the old status has been edited.
        claims["TEST-NEW"] = dict(claims["EXT-001"], id="TEST-NEW", supersedes=["EXT-001"])
        with patch.object(graph, "read_claims", return_value=claims):
            self.assertNotIn("EXT-001", {c["id"] for c in graph.search([], for_plan=True)})
            self.assertEqual(graph.show("EXT-001")["replaced_by"], ["TEST-NEW"])
            self.assertIn("EXT-001", graph.show("R01")["needs_basis_review"])
            with self.assertRaises(ValueError):
                kitchen.card("R01")
            with self.assertRaises(ValueError):
                graph.check()
        claims["EXT-016"]["lifecycle"] = "withdrawn"
        with patch.object(graph, "read_claims", return_value=claims):
            self.assertNotIn("APP-001", {c["id"] for c in graph.search([], for_plan=True)})

    def test_portable_references(self):
        for file in ROOT.rglob("*.md"):
            for target in re.findall(r"\[[^\]]+\]\(([^)]+)\)", file.read_text()):
                if not target.startswith(("http:", "https:", "#")):
                    self.assertTrue((file.parent / target).exists(), (file.name, target))
        blank = json.loads((ROOT / "assets/member-template.json").read_text())
        self.assertIsNone(blank["member_id"])
        self.assertTrue(all(blank[k] is None for k in ["medications","current_stage","allergies_and_cross_contact"]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
