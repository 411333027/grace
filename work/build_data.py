# /// script
# requires-python = ">=3.10"
# dependencies = ["pandas"]
# ///
"""
把 data/ 裡的三份標準 CSV（在學人數、休學人數、系所對照表）整理、加總成
網頁可以直接 <script src> 載入的 docs/data.js（不經過伺服器、不用 fetch，
雙擊 docs/index.html 就能在瀏覽器打開）。

用法：
  uv run work/build_data.py
"""
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
DST = ROOT / "docs" / "data.js"


def build_enrollment() -> list[dict]:
    df = pd.read_csv(DATA / "enrollment.csv", encoding="utf-8-sig")
    agg = (
        df.groupby(["semester", "college", "dept", "degree", "gender"], as_index=False)["count"]
        .sum()
    )
    return agg.to_dict(orient="records")


def build_leave() -> list[dict]:
    df = pd.read_csv(DATA / "leave.csv", encoding="utf-8-sig")
    agg = (
        df.groupby(
            ["semester", "college", "dept", "degree", "gender", "reason"], as_index=False
        )[["new_leave", "on_leave_end"]]
        .sum()
    )
    agg = agg.rename(columns={"new_leave": "newLeave", "on_leave_end": "onLeaveEnd"})
    return agg.to_dict(orient="records")


def build_dept_aliases() -> list[dict]:
    df = pd.read_csv(DATA / "dept_mapping.csv", encoding="utf-8-sig")
    records = []
    for _, row in df.iterrows():
        aliases_raw = row["aliases"]
        aliases = [a for a in str(aliases_raw).split(";") if a] if pd.notna(aliases_raw) else []
        records.append({"dept": row["dept"], "college": row["college"], "aliases": aliases})
    return records


def main():
    data = {
        "enrollment": build_enrollment(),
        "leave": build_leave(),
        "deptAliases": build_dept_aliases(),
    }

    # 核對：114-1 在學人數合計應該是 10035 人
    total_114_1 = sum(r["count"] for r in data["enrollment"] if r["semester"] == "114-1")
    assert total_114_1 == 10035, f"114-1 在學人數合計應為 10035，實際為 {total_114_1}"

    DST.parent.mkdir(parents=True, exist_ok=True)
    js = "window.BI_DATA = " + json.dumps(data, ensure_ascii=False, separators=(",", ":")) + ";\n"
    DST.write_text(js, encoding="utf-8")

    size_kb = DST.stat().st_size / 1024
    print(f"寫出 {DST}（{size_kb:.1f} KB）")
    print(f"enrollment {len(data['enrollment'])} 列，leave {len(data['leave'])} 列，"
          f"deptAliases {len(data['deptAliases'])} 筆")
    print(f"114-1 在學人數合計：{total_114_1}（驗證通過）")


if __name__ == "__main__":
    main()
