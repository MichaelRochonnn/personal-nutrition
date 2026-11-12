"""Build and inspect the local, reference-preserving nutrition graph. Python 3.9+."""
import argparse
import hashlib
import json
import re
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REF = ROOT / "references"
FIELDS = "id subject relation object summary population scenes conditions quantity limits source locator nature evidence status checked links".split()


def rows(name):
    return [json.loads(line) for line in (REF / name).read_text().splitlines() if line.strip()]


def indexed(records):
    result = {}
    for item in records:
        if item["id"] in result:
            raise ValueError("重复编号 " + item["id"])
        result[item["id"]] = item
    return result


def read_claims():
    return indexed(c for f in sorted(REF.glob("*-claims.jsonl")) for c in rows(f.name))


def read_sources():
    books = [json.loads(f.read_text()) for f in sorted(REF.glob("*-source.json"))]
    return indexed(books + json.loads((REF / "external-sources.json").read_text()))


def retired_ids(claims):
    retired = {c["id"] for c in claims.values()
               if c.get("lifecycle") in {"superseded", "withdrawn"}}
    for c in claims.values():
        retired.update(c.get("supersedes", []))
    return retired


def inactive_basis(claims):
    """A derived planning rule also needs review when a component has been retired."""
    inactive = retired_ids(claims)
    while True:
        additions = {c["id"] for c in claims.values() if c["source"] == "APP"
                     and inactive.intersection(c["links"])}
        if additions.issubset(inactive):
            return inactive
        inactive.update(additions)


def parts(value):
    if isinstance(value, list):
        return value
    return [p.strip() for p in re.split("[、，,；;]", value) if p.strip()]


def aliases():
    lookup = {}
    for term in rows("glossary.jsonl"):
        for variant in [term["name"], term["en"]] + term["aliases"]:
            key = variant.casefold()
            if key in lookup and lookup[key] != term:
                raise ValueError("同义词冲突 " + variant)
            lookup[key] = term
    return lookup


def variants(word, dictionary):
    term = dictionary.get(word.casefold())
    return [word.casefold()] if not term else [w.casefold() for w in [term["name"], term["en"]] + term["aliases"]]


def entity_key(name):
    return "E-" + hashlib.sha256(name.encode()).hexdigest()[:16]


def graph():
    dictionary = aliases()
    nodes, edges = {}, []

    def entity(label, kind):
        term = dictionary.get(label.casefold(), {})
        name = term.get("name", label)
        key = entity_key(name)
        if key in nodes and nodes[key]["name"] != name:
            raise ValueError("实体散列冲突 " + key)
        node = nodes.setdefault(key, {"id": key, "name": name, "types": []})
        category = term.get("type", kind)
        if category not in node["types"]:
            node["types"].append(category)
        return key

    def edge(left, relation, right, claim=None):
        item = {"from": left, "relation": relation, "to": right}
        if claim:
            item["claim"] = claim
        edges.append(item)

    for term in rows("glossary.jsonl"):
        entity(term["name"], term["type"])
    for source in read_sources().values():
        nodes[source["id"]] = {"id": source["id"], "name": source["title"], "types": ["来源"]}
    claims = read_claims()
    for key, c in claims.items():
        nodes[key] = {"id": key, "name": c["summary"], "types": ["主张"]}
        subject = entity(c["subject"], "知识概念")
        obj = entity(c["object"], "知识概念")
        edge(subject, c["relation"], obj, key)
        edge(key, "主体", subject)
        edge(key, "客体", obj)
        edge(key, "来源", c["source"])
        for field, kind in [("population", "适用人群"), ("scenes", "场景")]:
            for item in parts(c[field]):
                edge(key, kind, entity(item, kind))
        for link in c["links"]:
            edge(key, "参见", link)
        for link in c.get("supersedes", []):
            edge(key, "取代", link)
    for r in rows("harvard-recipes.jsonl"):
        nodes[r["id"]] = {"id": r["id"], "name": r["name_zh"], "types": ["原书食谱"]}
        edge(r["id"], "来源", r["source"])
    for r in rows("relations.jsonl"):
        nodes[r["id"]] = {"id": r["id"], "name": r["topic"], "types": [r["kind"]]}
        for member in r["claims"]:
            edge(r["id"], r["kind"], member)
    foods = indexed(json.loads((REF / "foods.json").read_text()))
    for food in foods.values():
        key = entity(food["name"], "食材")
        edge(key, "食物类别", entity(food["group"], "食物类别"))
    for recipe in rows("recipes.jsonl"):
        key = recipe["id"]
        nodes[key] = {"id": key, "name": recipe["name"], "types": ["食谱"]}
        for i in recipe["ingredients"]:
            edge(key, "使用", entity(foods[i["food"]]["name"], "食材"))
        for ref in recipe["basis"]:
            edge(key, "根据原则设计", ref)
    for rule in rows("substitutions.jsonl"):
        key = rule["id"]
        nodes[key] = {"id": key, "name": rule["from"] + " → " + rule["to"], "types": ["条件替换"]}
        for field, rel in [("from", "原食材"), ("to", "候选替代")]:
            edge(key, rel, entity(rule[field], "食材"))
        for ref in rule["basis"]:
            edge(key, "依据", ref)
    for item in edges:
        for key in ["from", "to", "claim"]:
            if key in item and item[key] not in nodes:
                raise ValueError("悬空引用 " + str(item))
    return sorted(nodes.values(), key=lambda n: n["id"]), edges


def encoded(values):
    return "".join(json.dumps(v, ensure_ascii=False) + "\n" for v in values)


def check(build=False):
    claims, sources = read_claims(), read_sources()
    retired = retired_ids(claims)
    for c in claims.values():
        absent = [k for k in FIELDS if k not in c or (not c[k] and k != "links")]
        if absent:
            raise ValueError(f"{c['id']} 缺项 {absent}")
        date.fromisoformat(c["checked"])
        if c["source"] not in sources:
            raise ValueError(c["source"])
        if c["id"] in c.get("supersedes", []) or set(c.get("supersedes", [])) - set(claims):
            raise ValueError("无效的主张版本引用 " + c["id"])
    for fname in ["relations.jsonl", "recipes.jsonl", "substitutions.jsonl"]:
        for item in indexed(rows(fname)).values():
            refs = item.get("basis", item.get("claims"))
            if not refs or set(refs) - set(claims):
                raise ValueError("依据不存在 " + item["id"])
            if fname != "relations.jsonl" and retired.intersection(refs):
                raise ValueError("在用食谱或替换的依据已撤回/替代 " + item["id"])
    affected = inactive_basis(claims) - retired
    if affected:
        raise ValueError("需重新评估应用主张 " + ", ".join(sorted(affected)))
    nodes, edges = graph()
    for filename, values in [("entities.jsonl", nodes), ("graph.jsonl", edges)]:
        target = REF / filename
        content = encoded(values)
        if build:
            tmp = target.with_suffix(".tmp")
            tmp.write_text(content)
            tmp.replace(target)
        elif not target.exists() or target.read_text() != content:
            raise ValueError("索引需重建 " + filename)
    print(f"{len(sources)} 来源，{len(claims)} 主张，{len(nodes)} 实体/记录节点，{len(edges)} 条边；引用有效。")


def discussions(key):
    return [r for r in rows("relations.jsonl") if key in r["claims"]]


def reference_only(c):
    flags = {c.get("decision_use"), c.get("planning_use"), c.get("lifecycle")}
    return bool(flags & {"quarantined", "historical_only", "historical_context",
                         "superseded", "withdrawn"}) or c["id"] in {"CN-037", "CN-044"}


def show(key):
    claims = read_claims()
    if key in claims:
        c = claims[key]
        return {"claim": c, "historical_or_review_only": reference_only(c) or key in inactive_basis(claims),
                "replaced_by": [x["id"] for x in claims.values() if key in x.get("supersedes", [])],
                "source_record": read_sources()[c["source"]], "discussions": discussions(key)}
    if key in read_sources():
        return read_sources()[key]
    for filename in ["relations.jsonl", "recipes.jsonl", "harvard-recipes.jsonl", "substitutions.jsonl", "entities.jsonl"]:
        found = indexed(rows(filename)).get(key)
        if found:
            if "basis" in found:
                found["needs_basis_review"] = sorted(inactive_basis(claims).intersection(found["basis"]))
            return found
    raise ValueError("未找到编号 " + key)


def search(words, population="", scene="", for_plan=False):
    dictionary = aliases()
    hits = []
    claims = read_claims()
    retired = inactive_basis(claims)
    for c in claims.values():
        if c["id"] in retired or (for_plan and reference_only(c)):
            continue
        def contains(value, word):
            return any(w in str(value).casefold() for w in variants(word, dictionary))
        if population and not contains(c["population"], population):
            continue
        if scene and not contains(c["scenes"], scene):
            continue
        fields = [str(c[k]).casefold() for k in ["subject", "object", "summary", "population", "scenes", "conditions", "limits", "quantity"]]
        scores = [sum(weight for field, weight in zip(fields, [8, 6, 5, 3, 3, 1, 1, 1]) if contains(field, w)) for w in words]
        if scores and not all(scores):
            continue
        score = sum(scores)
        hits.append((score, c))
    return [c for score, c in sorted(hits, key=lambda item: (-item[0], not item[1]["id"].startswith("EXT"), item[1]["id"]))]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="cmd", required=True)
    commands.add_parser("build")
    commands.add_parser("validate")
    lookup = commands.add_parser("search")
    lookup.add_argument("words", nargs="*")
    lookup.add_argument("--population", default="")
    lookup.add_argument("--scene", default="")
    lookup.add_argument("--limit", type=int, default=12)
    lookup.add_argument("--for-plan", action="store_true", help="滤除隔离、纯历史及旧版参数")
    commands.add_parser("show").add_argument("id")
    commands.add_parser("conflicts").add_argument("query", nargs="?", default="")
    for mode in ("swap", "recipes"):
        commands.add_parser(mode).add_argument("query", nargs="?", default="")
    args = parser.parse_args()
    if args.cmd in {"build", "validate"}:
        return check(args.cmd == "build")
    if args.cmd == "show":
        print(json.dumps(show(args.id), ensure_ascii=False, indent=2))
    elif args.cmd in {"swap", "recipes"}:
        records = rows("substitutions.jsonl") if args.cmd == "swap" else rows("recipes.jsonl") + rows("harvard-recipes.jsonl")
        for item in records:
            if args.query.casefold() in str(item).casefold():
                title = item.get("name") or item.get("name_zh") or item["from"] + " → " + item["to"]
                print(item["id"], title, "｜", item.get("locator") or item.get("portion") or item["mode"])
    elif args.cmd == "conflicts":
        for r in rows("relations.jsonl"):
            if r["kind"] not in {"补充", "支持"} and args.query.casefold() in str(r).casefold():
                print(r["id"], r["topic"], "｜", r["decision"], "｜", ", ".join(r["claims"]))
    else:
        result = search(args.words, args.population, args.scene, args.for_plan)
        for c in result[:max(0, args.limit)]:
            flags = ["仅溯源" if reference_only(c) else "需检查适用性"] + [r["id"] for r in discussions(c["id"])]
            print(c["id"], c["summary"], "｜", c["locator"], "｜", ", ".join(flags))
        if not result:
            print("没有匹配。拆开人群、禁忌和场景查询，再检查其交集。")


if __name__ == "__main__":
    main()
