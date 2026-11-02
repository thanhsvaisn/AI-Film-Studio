"""Reproducible Thai dialogue prompt and conservative subtitle quality checks."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "tests" / "lin_banquet_shared_context.txt"
HAN = re.compile(r"[\u3400-\u9fff]")
NUMBERED = re.compile(r"^\s*(\d{1,3})\.\s*(.*)$")
SPEAKER = re.compile(r"^([^:：]{1,32})[:：]\s*")
BANNED = ("ทรงพระเจริญ", "พระพร", "พระบัญชา", "เจ้าหญิง", "ท่านหญิง")

# These are deliberately small checks: presence is necessary, not proof that a
# sentence is correct. A human still needs to review kinship and intent.
REQUIRED = {
    4: ("คุณหนูสาม", "นายท่าน"),
    6: ("ขอคารวะ",),
    9: ("ท่านลุง", "พี่น้องร่วมตระกูล"),
    10: ("ท่านอา", "หลินหยวน"),
    11: ("พี่เช่อ",),
    12: ("น้องเฟิง", "น้องหมิงเซวียน"),
    14: ("พี่เช่อ", "พี่สะใภ้"),
    15: ("ท่านพ่อ", "ลูกสะใภ้", "โล่กำบัง"),
    20: ("หลินหยวน", "ประมุขตระกูล"),
}
FORBIDDEN_BY_LINE = {
    6: ("ลุงขอคารวะหลาน",),  # The nephew greets his maternal uncle.
    8: ("เธอ",),  # Disrespectful reference to the speaker's mother here.
    10: ("พี่สะใภ้",),  # The heir is the eldest male cousin, Lin Yuan.
    15: ("สามีของฉัน",),  # 公公 is the speaker's father-in-law.
}


def source_lines() -> dict[int, str]:
    lines = {}
    for line in SOURCE.read_text(encoding="utf-8-sig").splitlines():
        match = NUMBERED.match(line)
        if match:
            lines[int(match.group(1))] = match.group(2)
    if sorted(lines) != list(range(1, 22)):
        raise ValueError("Expected exactly 21 numbered source lines")
    # 清儿 and 青儿 are homophones but refer to different characters.
    lines[5] = lines[5].replace("清儿", "婉清")
    # The cast map unambiguously identifies 大堂哥 here as 林远. Entity
    # resolution before translation prevents the model from guessing a role.
    lines[10] = lines[10].replace("你大堂哥", "林远")
    return lines


def make_prompt(indices: list[int]) -> str:
    source = source_lines()
    if any(index not in source for index in indices):
        raise ValueError("Line index outside 1..21")
    header = """把以下古装剧对白译成自然、准确的泰语。每个编号只对应一条译文，保留编号。人名、身份、亲属关系必须准确，不要输出说话人标签、解释或中文。不要使用泰国王室敬语。

人物：林震山=หลินเจิ้นซาน，林远=หลินหยวน（长子、顾青的丈夫），顾青=กู้ชิง（林震山的儿媳），林风=หลินเฟิง，林婉清=หลินหว่านชิง（三姐），林小满=หลินเสี่ยวหม่าน，林策=หลินเช่อ（林远的堂兄弟），苏明轩=ซูหมิงเซวียน（林震山的外甥、林婉清的表哥），小翠=เสี่ยวชุ่ย。表哥在第3句指苏明轩。大堂哥在第10句指林远。

称谓：远儿=หยวนเอ๋อร์；青儿=ชิงเอ๋อร์（顾青）；婉清=หว่านชิง（林婉清）；策儿=เช่อเอ๋อร์；三姐=พี่สาม；二哥=พี่รอง；大嫂/表嫂=พี่สะใภ้；明轩表哥=พี่หมิงเซวียน；明轩表弟=น้องหมิงเซวียน；策表哥/策哥=พี่เช่อ；风弟=น้องเฟิง；娘亲=ท่านแม่；大伯=ท่านลุง；二叔=ท่านอา；堂兄弟=พี่น้องร่วมตระกูล；三小姐=คุณหนูสาม；老爷=นายท่าน；请安=ขอคารวะ；家主=ประมุขตระกูล；挡箭牌=โล่กำบัง。顾青称公公为ท่านพ่อ，自称ลูกสะใภ้。苏明轩称舅舅暂用ท่านลุง（实际长幼待核）。第7句原文“你姑姑，也就是你娘”视角矛盾，只表达“你的母亲”，不要凭空创造人物。第10句家主是林远，第20句也是林远。

禁用：ทรงพระเจริญ、พระพร、พระบัญชา、เจ้าหญิง、ท่านหญิง。男声和女声的句尾礼貌词须与说话人一致；无法确定时不要强加ครับ/ค่ะ。

对白（冒号前是说话人，仅供理解，不要输出）："""
    return header + "\n" + "\n".join(f"{index}. {source[index]}" for index in indices)


def parse_output(raw: str) -> tuple[dict[int, str], list[str]]:
    lines = {}
    errors = []
    for line in raw.replace("[end of text]", "").splitlines():
        if not line.strip():
            continue
        match = NUMBERED.match(line)
        if not match:
            errors.append(f"unnumbered: {line[:100]}")
            continue
        index = int(match.group(1))
        body = SPEAKER.sub("", match.group(2)).strip()
        if index in lines:
            errors.append(f"duplicate line {index}")
        lines[index] = body
    return lines, errors


def check(lines: dict[int, str], expected: list[int]) -> dict:
    issues = {}
    for index in expected:
        body = lines.get(index, "")
        found = []
        if not body:
            found.append("missing")
        if HAN.search(body):
            found.append("Han character remains")
        for word in BANNED:
            if word in body:
                found.append(f"banned: {word}")
        for word in REQUIRED.get(index, ()):
            if word not in body:
                found.append(f"missing glossary: {word}")
        for word in FORBIDDEN_BY_LINE.get(index, ()):
            if word in body:
                found.append(f"wrong relationship: {word}")
        if found:
            issues[index] = found
    return {"expected": expected, "present": sorted(lines), "issues": issues}


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--lines", default="3,4,6,8,9,10,12,14,15,20")
    parser.add_argument("--prompt", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--clean", type=Path)
    args = parser.parse_args()
    indices = [int(value) for value in args.lines.split(",")]
    if args.prompt:
        args.prompt.write_text(make_prompt(indices), encoding="utf-8")
    if args.output:
        raw = args.output.read_text(encoding="utf-8-sig")
        lines, parse_errors = parse_output(raw)
        if args.clean:
            args.clean.write_text("\n".join(f"{i}. {lines[i]}" for i in indices if i in lines) + "\n", encoding="utf-8")
        report = check(lines, indices)
        report["parse_errors"] = parse_errors
        print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
