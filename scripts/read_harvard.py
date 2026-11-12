"""Read a claim or recipe at its original paragraphs in the user's own EPUB."""
import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from xml.etree import ElementTree
from zipfile import BadZipFile, ZipFile

REFERENCES = Path(__file__).resolve().parents[1] / "references"


def read_jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def paragraphs_for_id(record_id):
    filename = "harvard-recipes.jsonl" if record_id.startswith("HAR-R") else "harvard-claims.jsonl"
    records = read_jsonl(REFERENCES / filename)
    record = next((entry for entry in records if entry["id"] == record_id), None)
    if record is None:
        raise ValueError(f"未找到 {record_id}")
    locator = re.fullmatch(r"(ops/xhtml/ch\d+\.html)，正文 p\[(\d+)(?:–(\d+))?\]", record["locator"])
    if not locator:
        raise ValueError(f"无法解析定位 {record['locator']}")
    member, start, end = locator.groups()
    return member, int(start), int(end or start)


def check_edition(book):
    known = json.loads((REFERENCES / "harvard-source.json").read_text(encoding="utf-8"))["sha256"]
    with book.open("rb") as stream:
        digest = hashlib.sha256()
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    if known != digest.hexdigest():
        raise ValueError("文件指纹与建档版不同；先确认版本并更新定位，以免读错段落。")


def main():
    parser = argparse.ArgumentParser(description="从已建档的本地 EPUB 核对主张或原食谱；输出英文原文供本地阅读。")
    parser.add_argument("book", type=Path, help="用户本地提供的 EPUB 文件")
    parser.add_argument("id", help="如 HAR-008 或 HAR-R001")
    args = parser.parse_args()
    try:
        member, start, end = paragraphs_for_id(args.id)
        check_edition(args.book)
        with ZipFile(args.book) as archive:
            element = ElementTree.fromstring(archive.read(member))
        paragraphs = element.find("{*}body").findall(".//{*}p")
        if len(paragraphs) < end:
            raise ValueError("该文件中不存在记录的段落。")
        print(f"{args.id} · {member} · p[{start}–{end}]")
        for index in range(start, end + 1):
            paragraph = paragraphs[index - 1]
            # Preserve spaces around inline fractions, e.g. 3 followed by <sup>1</sup>/<sub>2</sub>.
            for sup in paragraph.findall(".//{*}sup"):
                if sup.text:
                    sup.text = " " + sup.text
            content = " ".join("".join(paragraph.itertext()).split())
            images = [img.get("src", "") for img in paragraph.findall(".//{*}img")]
            print(f"{index:>4}  {content}", *images)
    except (OSError, BadZipFile, ValueError, KeyError, ElementTree.ParseError) as exc:
        parser.exit(2, f"{exc}\n")


if __name__ == "__main__":
    main()
