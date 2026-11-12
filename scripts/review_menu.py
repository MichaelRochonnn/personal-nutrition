"""Review declared ingredients for each eater separately. Input via stdin or a file."""
import argparse
import json
import sys
from datetime import date

# Others remain literal terms; these are ingredient identities, not medical equivalences.
ALLERGEN_NAMES = {
    "牛奶蛋白": ("牛奶蛋白过敏", "奶蛋白", "牛奶", "乳蛋白", "酸奶", "酪蛋白", "乳清", "奶粉", "无乳糖牛奶", "milk", "casein", "whey"),
    "大豆": ("黄豆", "毛豆", "大豆蛋白", "豆腐", "豆干", "豆腐皮", "腐竹", "豆浆", "豆饮", "soy", "soya"),
    "小麦": ("全麦", "小麦粉", "wheat"),
    "蛋": ("鸡蛋", "鸭蛋", "蛋清", "蛋黄", "egg"),
    "花生": ("落花生", "peanut"),
    "芝麻": ("芝麻酱", "sesame", "tahini"),
    "鱼": ("鱼类", "鱼露", "三文鱼", "狭鳕", "fish"),
    "甲壳类": ("虾", "蟹", "shrimp", "crustaceans"),
}
LOOKUP = {alias.casefold(): group for group, words in ALLERGEN_NAMES.items()
          for alias in (group,) + words}


def canonical(values):
    if not isinstance(values, list) or not all(isinstance(v, str) and v.strip() for v in values):
        raise ValueError("配料/限制须为已确认的名称列表；未知请用 null")
    result = set()
    for value in values:
        name = value.strip().casefold()
        for suffix in ("蛋白过敏", "过敏症", "过敏", " allergy"):
            if name.endswith(suffix) and len(name) > len(suffix):
                # Keep an established protein name when possible.
                if name not in LOOKUP:
                    name = name[:-len(suffix)].strip()
                break
        result.add(LOOKUP.get(name, name))
    return result


def review(data):
    as_of = date.fromisoformat(data.get("as_of", date.today().isoformat())).isoformat()
    people = {}
    for member in data["members"]:
        key = member["member_id"]
        if not key or key in people:
            raise ValueError("成员编号缺失或重复")
        people[key] = member
    results = []
    for dish in data["dishes"]:
        if not dish["components"] or not dish["eaters"]:
            raise ValueError("每道菜需提供用餐成员和全部配料")
        for key in dish["eaters"]:
            m = people[key]
            blocked, pending = [], []
            planned = dish.get("planned_stage", {})
            if dish.get("stage_sensitive") and (not m.get("current_stage") or not planned.get(key)):
                pending.append("阶段相关菜单需确认当前生活阶段及原适用阶段")
            elif m.get("current_stage") and key not in planned:
                pending.append("缺少原计划适用阶段")
            elif planned.get(key) != m.get("current_stage"):
                pending.append("原计划与当前生活阶段不同，重审人群规则")
            confirmed = m.get("confirmed_at", {})
            refreshed = m.get("reconfirmed_for_this_plan", [])
            for field in ["allergies_and_cross_contact", "other_exclusions"]:
                if confirmed.get(field) != as_of and field not in refreshed:
                    pending.append("旧资料或日期缺失，请确认 " + field)
            if m.get("other_exclusions") is None:
                pending.append("其他禁忌尚未确认")
            if m.get("allergies_and_cross_contact") is None:
                pending.append("过敏信息未知")
            allergens = canonical(m.get("allergies_and_cross_contact") or [])
            restrictions = canonical(m.get("other_exclusions") or [])
            for vague in allergens.intersection({"乳糖", "海鲜", "海产品", "坚果", "豆类", "shellfish", "nuts"}):
                pending.append(f"核对 {vague} 的确切范围及相关衍生成分")
            for item in dish["components"]:
                name = item["name"]
                if item.get("contains") is None and (allergens or restrictions):
                    pending.append(f"{name} 的完整配料未知")
                present = canonical([name]) | canonical(item.get("contains") or [])
                cross = canonical(item.get("cross_contact") or [])
                reviewed = canonical(item.get("verified_for") or [])
                direct = (allergens | restrictions) & present
                if direct:
                    blocked.append(f"{name} 含 " + "、".join(sorted(direct)))
                if cross & allergens:
                    blocked.append(f"{name} 有交叉接触提示 " + "、".join(sorted(cross & allergens)))
                unresolved = (allergens | restrictions) - reviewed - direct
                if unresolved:
                    pending.append(f"{name} 待核 " + "、".join(sorted(unresolved)))
                if (allergens or restrictions) and not item.get("basis"):
                    pending.append(f"{name} 缺当次配料或制作核实依据")
                if allergens and item.get("cross_contact") is None:
                    pending.append(f"{name} 交叉接触未知")
            if (allergens or restrictions) and not dish.get("all_components_included"):
                pending.append("确认包括油、酱料、饮料、配菜及全部复合配料")
            if allergens and key not in dish.get("kitchen_checked_for", []):
                pending.append("按该成员核对夹具、锅、炸油与分餐流程")
            results.append({"dish": dish["name"], "member": key,
                            "result": "排除" if blocked else "待核" if pending else "已通过所列条件检查",
                            "blocked": blocked, "pending": pending})
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", nargs="?", default="-")
    args = parser.parse_args()
    try:
        if args.input == "-":
            request = json.load(sys.stdin)
        else:
            with open(args.input) as handle:
                request = json.load(handle)
        print(json.dumps(review(request), ensure_ascii=False, indent=2))
    except (ValueError, TypeError, KeyError, OSError) as error:
        sys.exit("无法检查：" + str(error))
