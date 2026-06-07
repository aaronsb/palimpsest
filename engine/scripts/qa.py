"""Deterministic QA over translated page JSON (the checkable half of step 8).
The cheap-VLM visual pass is separate. Usage: qa.py json_dir"""
import glob
import json
import re
import sys

SV_CHARS = re.compile(r"[åäöÅÄÖ]")
NUM = re.compile(r"\d+")


def check_page(pj):
    issues = []
    uids = [b["uid"] for b in pj["blocks"]]
    dup = {u for u in uids if uids.count(u) > 1}
    if dup:
        issues.append(("uid_dup", sorted(dup)))
    for b in pj["blocks"]:
        lng = b.get("lang", {})
        sv, en = lng.get("sv", ""), lng.get("en", "")
        if b.get("translate", True):
            if not en:
                issues.append(("untranslated", b["uid"]))
            elif SV_CHARS.search(en):
                issues.append(("leftover_swedish", b["uid"], SV_CHARS.findall(en)))
        # number drift: digits present in source should survive (part #s, torques).
        # Only meaningful when there IS a source; recovered blocks have empty sv.
        if sv.strip():
            sv_nums, en_nums = NUM.findall(sv), NUM.findall(en or sv)
            if sorted(sv_nums) != sorted(en_nums):
                issues.append(("number_drift", b["uid"], sv_nums, en_nums))
        if b["class"] in ("part_number", "identifier") and en and en != sv:
            issues.append(("part_number_altered", b["uid"], sv, en))
    return issues


def main(json_dir):
    total = 0
    for jf in sorted(glob.glob(f"{json_dir}/*.page.json")):
        pj = json.load(open(jf))
        iss = check_page(pj)
        total += len(iss)
        tag = f"p{pj['page']['pdf_page']}"
        if iss:
            print(f"--- {tag} ({len(iss)} issues) ---")
            for it in iss:
                print("   ", it)
        else:
            print(f"--- {tag}: clean ---")
    print(f"\nTOTAL deterministic issues: {total}")


if __name__ == "__main__":
    main(sys.argv[1])
