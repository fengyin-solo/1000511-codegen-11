"""分路不良复核测试概览：待复核/待补录/台账三个口径与复核动作都收在这里。

设计口径：
- 轨道电路主表是唯一事实源，台账（_track_review）按 track_id 去重保存最新一次复核结论；
- 同一区段重复复核时覆盖旧结论，台账恒为一条；
- 复核通过后区段转为「运用正常」并移出待办，不通过则继续留在待复核；
- 分路不良统计全部从主表实时计算，复核前后统计随动作一起变化；
- 没有分路灵敏度的分路不良设备进「待补录」桶，补录后回到待复核。
"""
from __future__ import annotations

import re
from datetime import date
from typing import Any

from app.store import store

TRACK_MODULE = "track"
REVIEW_MODULE = "_track_review"

REVIEW_RESULTS = ["通过", "不通过"]
REVIEW_REQUIRED = ["复测结论", "复核测试日", "复核人"]
BACKFILL_REQUIRED = ["分路灵敏度"]

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class TrackReviewService:
    # ---- 读取口径 ------------------------------------------------------

    def stats(self) -> dict[str, int]:
        """分路不良相关实时统计：全部从主表现算，保证复核后一起变化。"""
        tracks = store.rows(TRACK_MODULE)
        bad = [row for row in tracks if row.get("status") == "分路不良"]
        pending = [row for row in bad if str(row.get("分路灵敏度") or "").strip()]
        backfill = [row for row in bad if not str(row.get("分路灵敏度") or "").strip()]
        passed = [
            row
            for row in self.review_rows()
            if row.get("复测结论") == "通过"
        ]
        return {
            "分路不良区段": len(bad),
            "待复核": len(pending),
            "待补录": len(backfill),
            "累计复核通过": len(passed),
        }

    def list_overview(
        self,
        *,
        scope: str = "pending",
        keyword: str | None = None,
        system: str | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
        """返回概览明细。scope: pending（待复核）/ backfill（待补录）/ ledger（台账）。"""
        if scope == "ledger":
            rows = self._ledger_rows()
        elif scope == "backfill":
            rows = [
                self._decorate(track)
                for track in store.rows(TRACK_MODULE)
                if track.get("status") == "分路不良"
                and not str(track.get("分路灵敏度") or "").strip()
            ]
        else:
            rows = [
                self._decorate(track)
                for track in store.rows(TRACK_MODULE)
                if track.get("status") == "分路不良"
                and str(track.get("分路灵敏度") or "").strip()
            ]
            # 待复核：先按分路灵敏度升序，再按制式类型升序
            rows.sort(key=lambda row: (self._sensitivity(row), str(row.get("制式类型") or ""), int(row["id"])))

        if keyword:
            rows = [
                row
                for row in rows
                if keyword in str(row.get("设备编号") or "")
                or keyword in str(row.get("所属区段") or "")
            ]
        if system:
            rows = [row for row in rows if system in str(row.get("制式类型") or "")]
        return rows, len(rows)

    def get_track(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(TRACK_MODULE, entry_id)

    # ---- 复核动作 ------------------------------------------------------

    def submit_review(
        self, entry_id: int, values: dict[str, Any]
    ) -> tuple[dict[str, Any] | None, str, dict[str, dict[str, str]], dict[str, Any]]:
        """提交一次复核。

        返回 (entry, message, field_errors, stats)：字段校验不过时 field_errors 标出每个
        不合规字段，前端据此高亮并允许修正后重试；stats 携带复核前后分路不良统计快照。
        """
        before = self.stats()
        track = store.find(TRACK_MODULE, entry_id)
        if track is None:
            return None, f"轨道电路 {entry_id} 不存在或已归档", {}, self._snapshot(before, before)
        if track.get("status") != "分路不良":
            return (
                None,
                "只有「分路不良」状态的区段需要复核，当前状态：" + str(track.get("status")),
                {},
                self._snapshot(before, before),
            )

        cleaned: dict[str, str] = {}
        errors: dict[str, str] = {}
        for field in REVIEW_REQUIRED:
            value = str(values.get(field) or "").strip()
            cleaned[field] = value
            if not value:
                errors[field] = "必填项不能为空"

        result = cleaned.get("复测结论", "")
        if result and result not in REVIEW_RESULTS:
            errors["复测结论"] = "复测结论只能是「通过」或「不通过」"

        test_date = cleaned.get("复核测试日", "")
        if test_date:
            if not DATE_RE.match(test_date):
                errors["复核测试日"] = "复核测试日格式应为 YYYY-MM-DD"
            else:
                try:
                    parsed = date.fromisoformat(test_date)
                except ValueError:
                    errors["复核测试日"] = "复核测试日不是合法日期"
                else:
                    if parsed > date.today():
                        errors["复核测试日"] = "复核测试日不能晚于今天"

        # 分路残压：结论为通过时必填，且不得超过该制式的残压限值
        residual_raw = str(values.get("分路残压") or "").strip()
        residual: float | None = None
        if residual_raw:
            try:
                residual = float(residual_raw)
            except ValueError:
                errors["分路残压"] = "分路残压应为数字（V）"
            else:
                if residual < 0:
                    errors["分路残压"] = "分路残压不能为负数"
        if result == "通过":
            if not residual_raw:
                errors["分路残压"] = "复核通过时必须填写分路残压实测值"
            elif residual is not None:
                limit_raw = str(track.get("残压限值") or "").strip()
                if limit_raw:
                    try:
                        limit = float(limit_raw)
                    except ValueError:
                        limit = None
                    if limit is not None and residual > limit:
                        errors["分路残压"] = f"分路残压 {residual:g}V 超过残压限值 {limit:g}V，不能判为通过"

        if errors:
            return None, "复核结论校验未通过，请修正标红项后重试", errors, self._snapshot(before, before)

        # 台账按 track_id upsert：同一区段重复复核只保留最新一次结论
        review = self._find_review(entry_id)
        if review is None:
            rows = store.rows(REVIEW_MODULE)
            review = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1, "track_id": entry_id}
            rows.append(review)
        review.update(
            {
                "设备编号": track.get("设备编号"),
                "所属区段": track.get("所属区段"),
                "复测结论": result,
                "上次测试日": track.get("上次测试日"),
                "复核测试日": test_date,
                "复核人": cleaned["复核人"],
                "分路残压": "" if residual is None else f"{residual:g}",
            }
        )

        # 主表联动：通过则转运用正常并移出待办；不通过保持分路不良、留在待复核
        track["复测结论"] = result
        track["复核测试日"] = test_date
        if result == "通过":
            track["status"] = "运用正常"
            track["pending"] = True
            track["abnormal"] = False
            track["上次测试日"] = test_date
            message = f"复核通过，{track.get('设备编号')} 已从待办移除"
        else:
            message = f"复核不通过，{track.get('设备编号')} 继续留在待复核清单"

        after = self.stats()
        return self._decorate(track), message, {}, self._snapshot(before, after)

    def backfill_sensitivity(
        self, entry_id: int, values: dict[str, Any]
    ) -> tuple[dict[str, Any] | None, str, dict[str, str]]:
        """为没有分路灵敏度的设备补录，补录成功后设备自动回到待复核桶。"""
        track = store.find(TRACK_MODULE, entry_id)
        if track is None:
            return None, f"轨道电路 {entry_id} 不存在或已归档", {}
        if str(track.get("分路灵敏度") or "").strip():
            return None, "该设备已登记分路灵敏度，无需补录", {}

        value = str(values.get("分路灵敏度") or "").strip()
        errors: dict[str, str] = {}
        if not value:
            errors["分路灵敏度"] = "分路灵敏度不能为空"
        else:
            try:
                number = float(value)
            except ValueError:
                errors["分路灵敏度"] = "分路灵敏度应为数字（Ω）"
            else:
                if number <= 0:
                    errors["分路灵敏度"] = "分路灵敏度应为正数"
        if errors:
            return None, "补录校验未通过，请修正后重试", errors

        track["分路灵敏度"] = f"{float(value):g}"
        return self._decorate(track), f"分路灵敏度已补录，{track.get('设备编号')} 已进入待复核清单", {}

    # ---- 内部辅助 ------------------------------------------------------

    def review_rows(self) -> list[dict[str, Any]]:
        return store.rows(REVIEW_MODULE)

    def _find_review(self, track_id: int) -> dict[str, Any] | None:
        for row in self.review_rows():
            if int(row.get("track_id", 0)) == track_id:
                return row
        return None

    def _ledger_rows(self) -> list[dict[str, Any]]:
        """台账：每个有复核结论的区段一条（台账本身按 track_id 去重），最新结论排在前。"""
        rows: list[dict[str, Any]] = []
        for review in self.review_rows():
            track = store.find(TRACK_MODULE, int(review.get("track_id", 0)))
            if track is not None:
                decorated = self._decorate(track)
                rows.append(decorated)
        rows.sort(key=lambda row: str(row.get("复核测试日") or ""), reverse=True)
        return rows

    def _decorate(self, track: dict[str, Any]) -> dict[str, Any]:
        """在主表记录上拼出概览需要的最新复核结论与相邻区段提示。"""
        row = dict(track)
        review = self._find_review(int(track.get("id", 0)))
        if review is not None:
            row["复测结论"] = review.get("复测结论")
            row["复核测试日"] = review.get("复核测试日")
        row["相邻区段提示"] = self._adjacency_hint(track)
        return row

    def _adjacency_hint(self, track: dict[str, Any]) -> str:
        """提示同站相邻区段以前有没有分路不良：当前状态或历史台账结论命中即提示。"""
        station = str(track.get("所属区段") or "").split("-", 1)[0]
        if not station:
            return ""
        same_station = sorted(
            (row for row in store.rows(TRACK_MODULE) if str(row.get("所属区段") or "").startswith(station + "-")),
            key=lambda row: int(row.get("id", 0)),
        )
        index = next(
            (i for i, row in enumerate(same_station) if int(row.get("id", 0)) == int(track.get("id", 0))),
            None,
        )
        if index is None:
            return ""
        hints: list[str] = []
        for neighbor in (same_station[index - 1] if index > 0 else None,
                         same_station[index + 1] if index + 1 < len(same_station) else None):
            if neighbor is None:
                continue
            review = self._find_review(int(neighbor.get("id", 0)))
            if neighbor.get("status") == "分路不良":
                hints.append(f"{neighbor.get('所属区段')} 当前分路不良")
            elif review is not None:
                hints.append(
                    f"{neighbor.get('所属区段')} 曾判{review.get('复测结论')}"
                    f"（{review.get('复核测试日')}）"
                )
        return "；".join(hints)

    @staticmethod
    def _sensitivity(row: dict[str, Any]) -> float:
        try:
            return float(str(row.get("分路灵敏度") or 0))
        except ValueError:
            return 0.0

    @staticmethod
    def _snapshot(before: dict[str, int], after: dict[str, int]) -> dict[str, Any]:
        return {"before": before, "after": after}
