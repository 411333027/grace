# /// script
# requires-python = ">=3.10"
# dependencies = ["pandas", "xlrd"]
# ///
"""
把「東華大學統計資料/在學人數統計表/」114-1 的 .xls 轉成整齊的 CSV。

用法：
  uv run work/etl_enrollment.py
"""
import re
from pathlib import Path

import pandas as pd
import xlrd

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "東華大學統計資料" / "在學人數統計表" / "114-1在學生人數統計表1141020--網路公告-10035人.xls"
DST = ROOT / "work" / "enrollment_114-1.csv"

# 欄位位置（依報表固定版面）：
COL_PROGRAM = 0  # 學制別（只在每個學制區塊的合計列標示，如「博士班 合計1」）
COL_COLLEGE = 1  # 學院（合併儲存格，只有範圍第一格有值）
COL_DEPT = 2     # 當學期系所全名（合併儲存格，只有範圍第一格有值）
COL_FEMALE = 5   # 「總計」欄位下的女生人數
COL_MALE = 6     # 「總計」欄位下的男生人數

PROGRAM_MAP = {
    "博士班": "博士班",
    "碩士班": "碩士班",
    "碩專班": "碩士在職專班",
    "學士班": "學士班",
}


def strip_annotation(s: str) -> str:
    """去掉括號裡的註記，例如「環境暨海洋學院(111更名)」->「環境暨海洋學院」"""
    return re.sub(r"[（(].*?[）)]", "", str(s)).strip()


def resolve_merged_column(sheet, col_idx: int) -> list:
    """把某一欄的合併儲存格值往下補齊。

    原始報表裡「學院」「系所」用合併儲存格表示同一組，值只放在合併範圍的第一格。
    但報表本身有一格該合併卻忘了合併（114-1 物理學系「應用物理博士班一般組」那一列），
    變成既不是合併範圍、格子本身也是空的「孤兒」，若單純用「往下補齊」(ffill) 會誤併入
    前一個系所。這裡改用真正的合併儲存格範圍來補值，遇到孤兒空格則改用「往下一個非空值
    回補」(bfill)，因為孤兒格永遠緊接在下一組資料之前。
    """
    merges = [(r1, r2) for (r1, r2, c1, c2) in sheet.merged_cells if c1 == col_idx]
    resolved = [None] * sheet.nrows
    for r in range(sheet.nrows):
        v = sheet.cell_value(r, col_idx)
        if v != "":
            resolved[r] = v
        else:
            merge = next(((r1, r2) for (r1, r2) in merges if r1 <= r < r2), None)
            if merge:
                resolved[r] = sheet.cell_value(merge[0], col_idx)
    # 孤兒空格（不屬於任何合併範圍）：往後找最近的已知值回補
    last = None
    for r in range(sheet.nrows - 1, -1, -1):
        if resolved[r] is not None:
            last = resolved[r]
        elif last is not None:
            resolved[r] = last
    return resolved


def main():
    book = xlrd.open_workbook(SRC, formatting_info=True)
    sheet = book.sheet_by_index(0)
    college_resolved = resolve_merged_column(sheet, COL_COLLEGE)
    dept_resolved = resolve_merged_column(sheet, COL_DEPT)

    df = pd.read_excel(SRC, sheet_name=0, header=None)
    df[COL_COLLEGE] = college_resolved
    df[COL_DEPT] = dept_resolved

    col0 = df[COL_PROGRAM].astype("string")

    # 資料範圍：從「總計=1+2+3+4」之後開始，到「備註：」之前結束
    total_idx = col0[col0.str.strip() == "總計=1+2+3+4"].index[0]
    note_idx = col0[col0.str.contains("備註", na=False)].index[0]
    data = df.iloc[total_idx + 1 : note_idx].copy()

    raw_program = data[COL_PROGRAM].astype("string")  # ffill 前的原始值，用來找出小計列
    is_subtotal = raw_program.str.contains("合計", na=False)

    # 學制別是合併儲存格，往下補齊（這欄沒有孤兒空格問題，直接 ffill 即可）
    data[COL_PROGRAM] = data[COL_PROGRAM].ffill()

    program_raw = data[COL_PROGRAM].astype(str).str.replace(r"\s*合計\d+$", "", regex=True)
    data["program_raw"] = program_raw.map(PROGRAM_MAP)

    # 排除總計、合計列（小計列本身沒有系所，只是區塊標記）
    data = data[~is_subtotal]

    data["college"] = data[COL_COLLEGE].map(strip_annotation)
    data["dept_raw"] = data[COL_DEPT].astype(str).str.strip()
    data["female"] = pd.to_numeric(data[COL_FEMALE], errors="coerce").fillna(0).astype(int)
    data["male"] = pd.to_numeric(data[COL_MALE], errors="coerce").fillna(0).astype(int)

    # 同一系所、同一學制下可能有多個「分組」（col3），要加總成一列
    long = pd.concat(
        [
            data[["college", "dept_raw", "program_raw"]].assign(gender="女", count=data["female"]),
            data[["college", "dept_raw", "program_raw"]].assign(gender="男", count=data["male"]),
        ],
        ignore_index=True,
    )
    out = (
        long.groupby(["college", "dept_raw", "program_raw", "gender"], as_index=False)["count"]
        .sum()
        .sort_values(["college", "dept_raw", "program_raw", "gender"])
        .reset_index(drop=True)
    )

    out.to_csv(DST, index=False, encoding="utf-8-sig")
    print(f"寫出 {len(out)} 列到 {DST}")


if __name__ == "__main__":
    main()
