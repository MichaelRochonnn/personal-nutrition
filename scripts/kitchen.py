"""菜谱与购物清单、按标签的营养估算。只读本地文件，不保存成员资料。"""
import argparse
import json
import math
from pathlib import Path
import graph

REF = Path(__file__).resolve().parents[1] / "references"
CATEGORIES = ("food", "oil", "salt", "condiment", "drink")
MEASURE_UNITS = {"g", "mL"}
NUTRIENT_UNITS = {"g", "mg", "µg", "kcal", "kJ", "IU"}


def number(value, label, positive=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} 须为数字，未知请用 null")
    if not math.isfinite(value) or value < 0 or (positive and value == 0):
        raise ValueError(f"{label} 数值或范围无效")
    return value


def nonempty(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"缺少{label}")
    return value.strip()


def catalog():
    foods = json.loads((REF / "foods.json").read_text(encoding="utf-8"))
    recipes = [json.loads(line) for line in (REF / "recipes.jsonl").read_text(encoding="utf-8").splitlines() if line]
    claims = graph.read_claims()
    unavailable = graph.inactive_basis(claims)
    usable = {r["id"]: r for r in recipes if set(r["basis"]) <= claims.keys()
              and not unavailable.intersection(r["basis"])}
    return usable, {f["id"]: f for f in foods}


def portions(people):
    if type(people) is not int or people < 1:
        raise ValueError("人数须为正整数")
    return people


def make_card(recipe_id, people, recipes, foods):
    if recipe_id not in recipes:
        raise ValueError(f"菜谱 {recipe_id} 不存在或其依据需复核")
    recipe = dict(recipes[recipe_id])
    parts = []
    for part in recipe["ingredients"]:
        food = foods[part["food"]]
        parts.append({**food, "amount": number(part["amount"] * people, "用量")})
    recipe["ingredients"] = parts
    recipe["people"] = people
    recipe["portion_note"] = "按每人一份起点等比例汇总用量；多人需按锅具容量重新估计烹调时间。"
    return recipe


def card(recipe_id, people=1):
    return make_card(recipe_id, portions(people), *catalog())


def shop(recipe_ids, people=1):
    portions(people)
    if not recipe_ids:
        raise ValueError("至少选一道菜")
    recipes, foods = catalog()
    shopping = {}
    for recipe_id in recipe_ids:
        for food in make_card(recipe_id, people, recipes, foods)["ingredients"]:
            key = (food["id"], food["state"], food["unit"])
            if key not in shopping:
                shopping[key] = {**food, "amount": 0}
            shopping[key]["amount"] += food["amount"]
    return {"people": people, "recipe_ids": recipe_ids, "items": list(shopping.values()),
            "note": "食谱净用量。重复菜谱重复计数，实际整包数、不可食部、损耗、库存与价格另核。"}


def measure(data, label, allow_unknown):
    if not isinstance(data, dict):
        raise ValueError(f"{label} 需标明数字、单位和食物状态")
    unit = data.get("unit")
    if unit not in MEASURE_UNITS:
        raise ValueError(f"{label} 仅能以可食部 g 或 mL 输入，份/枚/勺先用可靠依据换算")
    state = nonempty(data.get("state"), f"{label}的生熟、固液或沥干状态")
    if data.get("edible") is not True:
        raise ValueError(f"{label} 需要确认已换算到可食部")
    amount = data.get("amount")
    if amount is None and allow_unknown:
        return None, unit, state
    return number(amount, label, positive=not allow_unknown), unit, state


def item_estimate(item, targets):
    name = nonempty(item.get("name"), "食材名称")
    category = item.get("category")
    if category not in CATEGORIES:
        raise ValueError(f"{name} 分类无效，请使用 {', '.join(CATEGORIES)}")
    amount, unit, state = measure(item.get("portion"), name + "实际份量", True)
    basis = item.get("basis")
    values = {}
    scale = None
    if basis is not None:
        if not isinstance(basis, dict):
            raise ValueError(f"{name} 基准须为对象或 null")
        source = nonempty(item.get("source"), name + "的具体标签或成分表定位")
        if source.lower() in {"未知", "待填", "unknown", "n/a", "待核", "不详"}:
            raise ValueError(f"{name} 没有可追溯来源，basis 应设为 null")
        size, base_unit, base_state = measure(basis, name + "数据基准", False)
        if (unit, state) != (base_unit, base_state):
            raise ValueError(f"{name} 份量与来源的单位/状态不一致，不能混算")
        values = basis.get("values")
        if not isinstance(values, dict):
            raise ValueError(f"{name} values 须按营养素名称列示标签数值和单位")
        for nutrient, info in values.items():
            if info is None:
                continue
            if not isinstance(info, dict) or info.get("unit") not in NUTRIENT_UNITS:
                raise ValueError(f"{name} 的 {nutrient} 缺少可识别单位")
            if info.get("value") is not None:
                number(info["value"], name + nutrient)
        if amount is not None:
            scale = number(amount / size, name + "份量换算系数")

    result = {}
    for nutrient, target_unit in targets.items():
        info = values.get(nutrient)
        value = None
        if info is not None:
            if not isinstance(info, dict) or info.get("unit") != target_unit:
                raise ValueError(f"{name} 的 {nutrient} 单位须为 {target_unit}；先根据可靠依据统一口径")
            if info.get("value") is not None and scale is not None:
                value = number(info["value"] * scale, name + nutrient + "换算值")
        result[nutrient] = value
    return {"name": name, "category": category, "portion": item["portion"], "basis": basis,
            "source": item.get("source"), "estimated": result}


def nutrients(data):
    """对每种营养素独立合计。未计入的类别和未知格会阻止发布整餐总量。"""
    if not isinstance(data, dict):
        raise ValueError("餐次输入须是 JSON 对象")
    targets = data.get("targets")
    if not isinstance(targets, dict) or not targets:
        raise ValueError("targets 须列出至少一种营养素及统一单位")
    for key, unit in targets.items():
        nonempty(key, "营养素名称")
        if unit not in NUTRIENT_UNITS:
            raise ValueError(f"{key} 的单位无法识别，允许 {', '.join(sorted(NUTRIENT_UNITS))}")
        is_energy = key.strip().lower() in {"能量", "热量", "energy", "calories"}
        if is_energy and unit not in {"kcal", "kJ"}:
            raise ValueError(f"{key} 不能按质量或 IU 计算")
        if not is_energy and unit in {"kcal", "kJ"}:
            raise ValueError(f"能量项目请命名为“能量”或 energy；{key} 不能按 {unit} 计算")
    servings = number(data.get("servings", 1), "等分份数", positive=True)
    review = data.get("review", {})
    if not isinstance(review, dict) or set(review) - set(CATEGORIES):
        raise ValueError("review 分类无效")
    if not isinstance(data.get("items"), list) or not data["items"]:
        raise ValueError("items 至少列出一项食材或待核项目")
    if not all(isinstance(i, dict) for i in data["items"]):
        raise ValueError("每个用料条目须为 JSON 对象")
    rows = [item_estimate(item, targets) for item in data["items"]]
    categories = {i["category"] for i in rows}
    unchecked = []
    for category in CATEGORIES:
        status = review.get(category, "unknown")
        if status not in {"listed", "none", "unknown"}:
            raise ValueError(f"review.{category} 只能填 listed、none 或 unknown")
        if status == "unknown":
            unchecked.append(category)
        elif (status == "listed") != (category in categories):
            raise ValueError(f"review.{category} 与实际列出的食材不符")
    totals = {}
    for nutrient, unit in targets.items():
        missing = [i["name"] for i in rows if i["estimated"][nutrient] is None]
        missing += [f"未排查类别 {category}" for category in unchecked]
        known = [i["estimated"][nutrient] for i in rows if i["estimated"][nutrient] is not None]
        subtotal = number(math.fsum(known), nutrient + "小计") if known else None
        total = None if missing else subtotal
        totals[nutrient] = {"unit": unit, "known_subtotal": subtotal, "meal": total,
                            "per_serving": number(total / servings, nutrient + "每份值") if total is not None else None,
                            "missing": missing}
    return {"meal_name": data.get("meal_name"), "servings": servings, "items": rows,
            "review": {key: review.get(key, "unknown") for key in CATEGORIES}, "totals": totals,
            "note": "按可食份量和标示值估算，原标签有舍入。null 表示未知；每份按均匀等分，不适用于分量不同的成员。"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    cmds = parser.add_subparsers(dest="cmd", required=True)
    single = cmds.add_parser("card", help="完整食谱卡")
    single.add_argument("id")
    shopping = cmds.add_parser("shop", help="合并一餐或多餐的用料")
    shopping.add_argument("ids", nargs="+")
    for sub in (single, shopping):
        sub.add_argument("--people", type=int, default=1, help="每道菜的人数，默认1")
    calc = cmds.add_parser("nutrients", help="从实际标签/成分表与可食部用量估算")
    calc.add_argument("input", type=Path, help="参照 assets/nutrition-input.json 的本地 JSON")
    args = parser.parse_args()
    try:
        if args.cmd == "card":
            result = card(args.id, args.people)
        elif args.cmd == "shop":
            result = shop(args.ids, args.people)
        else:
            result = nutrients(json.loads(args.input.read_text(encoding="utf-8")))
        print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    except (OSError, ValueError, TypeError, KeyError, OverflowError) as exc:
        parser.exit(2, f"无法完成：{exc}\n")


if __name__ == "__main__":
    main()
