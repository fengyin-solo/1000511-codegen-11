"""分路不良复核测试业务规则：待复核台账、复测结论去重与统计口径都收在这里。

台账（track_review）按轨道电路设备一条记录保存最近一次复核结论；待办口径直接从
轨道电路（track）现状推导，保证其他入口改了设备状态后，本台账与轨道电路列表始终对得上。
"""
from __future__ import annotations

import re
from datetime import date
from typing import Any

from app.store import store

TRACK_MODULE = "track"
MODULE = "track_review"

SENSITIVITY_FIELD = "分路灵敏度"
BAD_STATUS = "分路不良"
NORMAL_STATUS = "运用正常"
RECHECK_PASS = "复核通过"
RECHECK_BAD = "复测仍不良"
CONCLUSIONS = [RECHECK_PASS, RECHECK_BAD]

DISPLAY_FIELDS = [
    "设备编号", "制式类型", "分路灵敏度", "所属区段",
    "上次测试日", "下次测试日", "设备状态",
]
LEDGER_FIELDS = ["复测日期", "复测结论", "复测人员"]
DATE_PATTERN = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _sensitivity_key(value: Any) -> tuple[int, float, str]:
    """分路灵敏度排序：能读出数字的按数字排（越小越靠前），读不出的排最后。"""
    text = _clean(value)
    match = re.search(r"\d+(?:\.\d+)?", text)
    if match:
        return (0, float(match.group()), text)
    return (1, 0.0, text)


class TrackReviewService:
    # ---- 台账视图拼装 -------------------------------------------------

    def _ledger_by_track(self) -> dict[int, dict[str, Any]]:
        return {int(row["track_id"]): row for row in store.rows(MODULE)}

    def _view_row(self, track: dict[str, Any], ledger: dict[str, Any] | None) -> dict[str, Any]:
        row: dict[str, Any] = {"id": int(track["id"])}
        for field in DISPLAY_FIELDS:
            row[field] = track.get(field)
        for field in LEDGER_FIELDS:
            row[field] = ledger.get(field) if ledger else None
        row["复核状态"] = self._review_state(track, ledger)
        return row

    def _review_state(self, track: dict[str, Any], ledger: dict[str, Any] | None) -> str:
        status = track.get("status")
        if status == BAD_STATUS:
            if not _clean(track.get(SENSITIVITY_FIELD)):
                return "待补录"
            if ledger and ledger.get("复测结论") == RECHECK_BAD:
                return "复测仍不良"
            return "待复核"
        if status == NORMAL_STATUS and ledger and ledger.get("复测结论") == RECHECK_PASS:
            return "复核通过"
        return str(status or "—")

    def _groups(self) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
        """返回（待复核、待补录、仅台账有记录的历史区段）三组，全部由轨道电路现状推导。"""
        tracks = store.rows(TRACK_MODULE)
        ledger_by_track = self._ledger_by_track()

        pending: list[dict[str, Any]] = []
        missing: list[dict[str, Any]] = []
        for track in tracks:
            if track.get("status") != BAD_STATUS:
                continue
            view = self._view_row(track, ledger_by_track.get(int(track["id"])))
            if _clean(track.get(SENSITIVITY_FIELD)):
                pending.append(view)
            else:
                missing.append(view)

        bad_ids = {int(row["id"]) for row in pending + missing}
        history: list[dict[str, Any]] = []
        track_by_id = {int(row["id"]): row for row in tracks}
        for ledger in store.rows(MODULE):
            track_id = int(ledger["track_id"])
            if track_id in bad_ids:
                continue  # 仍在待办里的，已由上面的现状分组承载
            track = track_by_id.get(track_id)
            if track is not None:
                history.append(self._view_row(track, ledger))

        # 待复核：先按分路灵敏度、再按制式类型排列；待补录：按制式类型排列
        pending.sort(key=lambda row: (
            _sensitivity_key(row[SENSITIVITY_FIELD]),
            _clean(row["制式类型"]),
            _clean(row["设备编号"]),
        ))
        missing.sort(key=lambda row: (_clean(row["制式类型"]), _clean(row["设备编号"])))
        return pending, missing, history

    def _ledger_rows(self) -> list[dict[str, Any]]:
        pending, missing, history = self._groups()
        rows = pending + missing + history
        # 台账：最近复测的排前面，没复测过的排后面
        rows.sort(key=lambda row: (
            0 if _clean(row.get("复测日期")) else 1,
            -self._date_ordinal(_clean(row.get("复测日期"))),
            _clean(row["设备编号"]),
        ))
        return rows

    @staticmethod
    def _date_ordinal(text: str) -> int:
        match = DATE_PATTERN.match(text)
        if not match:
            return 0
        try:
            return date(int(match.group(1)), int(match.group(2)), int(match.group(3))).toordinal()
        except ValueError:
            return 0

    # ---- 列表与统计 ---------------------------------------------------

    def list_entries(
        self,
        *,
        group: str = "pending",
        keyword: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        pending, missing, history = self._groups()
        if group == "missing":
            rows = missing
        elif group == "ledger":
            rows = self._ledger_rows()
        else:
            rows = pending
        if keyword:
            rows = [
                row for row in rows
                if keyword in _clean(row.get("设备编号")) or keyword in _clean(row.get("所属区段"))
            ]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def stats(self) -> dict[str, int]:
        pending, missing, history = self._groups()
        passed = sum(
            1 for row in history
            if row.get("复测结论") == RECHECK_PASS and row.get("设备状态") == NORMAL_STATUS
        )
        bad_now = len(pending) + len(missing)
        return {
            "分路不良（复核前）": bad_now + passed,
            "分路不良（复核后）": bad_now,
            "待复核": len(pending),
            "待补录": len(missing),
            "复核已通过": passed,
        }

    # ---- 动作 ---------------------------------------------------------

    def recheck(
        self, track_id: int, values: dict[str, Any]
    ) -> tuple[dict[str, Any] | None, str, dict[str, str]]:
        track = store.find(TRACK_MODULE, track_id)
        if track is None:
            return None, f"轨道电路 {track_id} 不存在或已归档", {"设备编号": "设备不存在或已归档"}

        errors: dict[str, str] = {}
        if track.get("status") != BAD_STATUS:
            errors["设备状态"] = f"当前状态为「{track.get('status')}」，只有分路不良区段需要复核"

        conclusion = _clean(values.get("复测结论"))
        if not conclusion:
            errors["复测结论"] = "请选择复测结论"
        elif conclusion not in CONCLUSIONS:
            errors["复测结论"] = f"复测结论只允许：{'、'.join(CONCLUSIONS)}"

        test_date = _clean(values.get("复测日期"))
        if not test_date:
            errors["复测日期"] = "请填写复测日期"
        elif not DATE_PATTERN.match(test_date):
            errors["复测日期"] = "复测日期格式应为 YYYY-MM-DD"
        else:
            match = DATE_PATTERN.match(test_date)
            try:
                parsed = date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
            except ValueError:
                errors["复测日期"] = "复测日期不是有效的日历日期"
                parsed = None
            if parsed and parsed > date.today():
                errors["复测日期"] = "复测日期不能晚于今天"

        operator = _clean(values.get("复测人员"))
        if not operator:
            errors["复测人员"] = "请填写复测人员"

        if not _clean(track.get(SENSITIVITY_FIELD)):
            errors["分路灵敏度"] = "该设备缺少分路灵敏度，请先在「待补录」中补录后再复核"

        if errors:
            return None, "复核结论校验未通过，请按标注修正后重试", errors

        # 同一设备只保留最新一次结论：已存在就原地更新
        ledger = self._ledger_by_track().get(track_id)
        if ledger is None:
            rows = store.rows(MODULE)
            ledger = {
                "id": max((int(row.get("id", 0)) for row in rows), default=0) + 1,
                "track_id": track_id,
            }
            rows.append(ledger)
        ledger["设备编号"] = track.get("设备编号")
        ledger["复测结论"] = conclusion
        ledger["复测日期"] = test_date
        ledger["复测人员"] = operator

        track["上次测试日"] = test_date
        track["设备状态"] = NORMAL_STATUS if conclusion == RECHECK_PASS else BAD_STATUS
        if conclusion == RECHECK_PASS:
            track["status"] = NORMAL_STATUS
            track["pending"] = False
            track["abnormal"] = False
        else:
            track["status"] = BAD_STATUS
            track["pending"] = True
            track["abnormal"] = True

        message = "复核通过，已移出待办" if conclusion == RECHECK_PASS else "复测仍分路不良，保留在待办"
        return self._view_row(track, ledger), message, {}

    def supplement(
        self, track_id: int, values: dict[str, Any]
    ) -> tuple[dict[str, Any] | None, str, dict[str, str]]:
        track = store.find(TRACK_MODULE, track_id)
        if track is None:
            return None, f"轨道电路 {track_id} 不存在或已归档", {"设备编号": "设备不存在或已归档"}
        if track.get("status") != BAD_STATUS:
            return None, f"设备当前状态为「{track.get('status')}」，无需补录", {"设备状态": "仅分路不良区段需要补录"}

        sensitivity = _clean(values.get(SENSITIVITY_FIELD))
        if not sensitivity:
            return None, "分路灵敏度不能为空", {SENSITIVITY_FIELD: "请填写分路灵敏度后再提交"}

        track[SENSITIVITY_FIELD] = sensitivity
        return self._view_row(track, self._ledger_by_track().get(track_id)), "分路灵敏度已补录，转入待复核", {}
