# -*- coding: utf-8 -*-
"""
生态瓶实验报告 PDF 导出（中小学生友好版）
中文字体使用项目内 static/fonts/msyh.ttc（微软雅黑）。
注意：雅黑不含彩色 emoji 字形，PDF 正文使用中文与标点，避免 tofu 方框。
"""
from __future__ import annotations

import io
import os
from datetime import datetime
from pathlib import Path
import html
from typing import Optional

from config import Config

# 与 run.py 启动横幅一致
SYSTEM_PLATFORM_NAME = (
    "香港科技大学（广州）-编程猫青少年AI教育联合实验室教学平台"
)

CHANNEL_META = [
    ("temperature", "温度", "°C"),
    ("humidity", "湿度", "%"),
    ("light", "光照", "lux"),
    ("oxygen", "氧气", "%"),
    ("solar_power", "发电量", "mW"),
    ("battery", "发电量", "mW"),  # 历史字段兼容
]


def _bundled_msyh_path() -> Path:
    return Path(Config.BASE_DIR) / "static" / "fonts" / "msyh.ttc"


def _find_cjk_font() -> Optional[str]:
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    if "EcoReportCN" in pdfmetrics.getRegisteredFontNames():
        return "EcoReportCN"

    p = _bundled_msyh_path()
    if not p.is_file():
        return None
    try:
        pdfmetrics.registerFont(TTFont("EcoReportCN", str(p), subfontIndex=0))
        return "EcoReportCN"
    except Exception:
        return None


def build_experiment_reports_pdf(reports: list) -> bytes:
    # 兼容低版本 OpenSSL：禁用 usedforsecurity
    try:
        import hashlib
        _orig_md5 = hashlib.md5
        def _safe_md5(*a, **k):
            k.pop('usedforsecurity', None)
            return _orig_md5(*a, **k)
        hashlib.md5 = _safe_md5
    except Exception:
        pass

    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_LEFT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import (
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    font = _find_cjk_font()
    if not font:
        raise RuntimeError(
            f"未找到项目字体文件：{_bundled_msyh_path()}。请将 msyh.ttc 放入 static/fonts/ 目录。"
        )

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        rightMargin=1.8 * cm,
        leftMargin=1.8 * cm,
        topMargin=1.2 * cm,
        bottomMargin=1.2 * cm,
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        name="EcoTitle",
        fontName=font,
        fontSize=16,
        leading=22,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#5B21B6"),
        spaceAfter=6,
    )
    sub_style = ParagraphStyle(
        name="EcoSub",
        fontName=font,
        fontSize=11,
        leading=15,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#6B7280"),
        spaceAfter=14,
    )
    h2_style = ParagraphStyle(
        name="EcoH2",
        fontName=font,
        fontSize=13,
        leading=18,
        textColor=colors.HexColor("#7C3AED"),
        spaceBefore=10,
        spaceAfter=6,
    )
    body_style = ParagraphStyle(
        name="EcoBody",
        fontName=font,
        fontSize=10,
        leading=14,
        alignment=TA_LEFT,
        textColor=colors.HexColor("#374151"),
    )
    tip_style = ParagraphStyle(
        name="EcoTip",
        fontName=font,
        fontSize=9,
        leading=13,
        textColor=colors.HexColor("#6B7280"),
        leftIndent=8,
        borderColor=colors.HexColor("#F59E0B"),
        borderWidth=0,
        backColor=colors.HexColor("#FFFBEB"),
        spaceBefore=4,
        spaceAfter=8,
    )

    story = []

    # 顶部色带（用表格模拟）
    banner = Table(
        [[Paragraph("<b>【生态瓶】实验报告汇总</b>", title_style)]],
        colWidths=[doc.width],
    )
    banner.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#EDE9FE")),
                ("TOPPADDING", (0, 0), (-1, -1), 10),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
                ("BOX", (0, 0), (-1, -1), 1.5, colors.HexColor("#A78BFA")),
            ]
        )
    )
    story.append(banner)
    story.append(Spacer(1, 0.35 * cm))

    story.append(Paragraph(html.escape(SYSTEM_PLATFORM_NAME), sub_style))
    export_t = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    story.append(
        Paragraph(f"<b>导出时间：</b>{export_t}　　<b>报告份数：</b>{len(reports)}", body_style)
    )
    story.append(Spacer(1, 0.4 * cm))

    if not reports:
        story.append(
            Paragraph("目前还没有保存的实验报告哦～先去「模型训练」里训练并保存分析报告吧！", body_style)
        )
        doc.build(story)
        return buf.getvalue()

    for i, rep in enumerate(reports, start=1):
        story.append(Paragraph(f"<b>实验 {i}</b>", h2_style))
        ts = rep.get("timestamp") or "—"
        ma = rep.get("model_analysis") or {}
        story.append(
            Paragraph(
                f"<b>记录时间：</b>{ts}　　<b>模型类型：</b>{ma.get('model_type', '—')}　　"
                f"<b>预处理：</b>{ma.get('preprocessing', '—')}　　<b>预测步长：</b>{ma.get('prediction_steps', '—')}",
                body_style,
            )
        )

        # 五通道数据概况（彩色小卡片表格）
        ds = rep.get("data_summary") or {}
        if ds:
            story.append(Paragraph("<b>本次用到的数据概况</b>", body_style))
            rows = [[Paragraph("<b>变量</b>", body_style), Paragraph("<b>数据条数</b>", body_style),
                     Paragraph("<b>平均</b>", body_style), Paragraph("<b>趋势</b>", body_style)]]
            for key, name, unit in CHANNEL_META:
                if key not in ds:
                    continue
                s = ds[key]
                mean_v = s.get("mean")
                mean_s = f"{mean_v:.2f}{unit}" if isinstance(mean_v, (int, float)) else "—"
                trend = s.get("trend") or "—"
                cnt = s.get("count", "—")
                label = name
                rows.append(
                    [
                        Paragraph(label, body_style),
                        Paragraph(str(cnt), body_style),
                        Paragraph(mean_s, body_style),
                        Paragraph(str(trend), body_style),
                    ]
                )
            if len(rows) > 1:
                t = Table(rows, colWidths=[doc.width * 0.28, doc.width * 0.18, doc.width * 0.22, doc.width * 0.22])
                t.setStyle(
                    TableStyle(
                        [
                            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#DDD6FE")),
                            ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#4C1D95")),
                            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#FAF5FF")]),
                            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E9D5FF")),
                            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                            ("LEFTPADDING", (0, 0), (-1, -1), 6),
                            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                            ("TOPPADDING", (0, 0), (-1, -1), 5),
                            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                        ]
                    )
                )
                story.append(t)
            story.append(Spacer(1, 0.2 * cm))

        mm = rep.get("model_metrics") or {}
        if mm:
            story.append(Paragraph("<b>模型评估（R² 越接近 1 越好）</b>", body_style))
            mrows = [[Paragraph("<b>通道</b>", body_style), Paragraph("<b>R²</b>", body_style),
                      Paragraph("<b>RMSE</b>", body_style), Paragraph("<b>MAE</b>", body_style)]]
            key_labels = {row[0]: row[1] for row in CHANNEL_META}
            for k, m in mm.items():
                if not isinstance(m, dict):
                    continue
                label = key_labels.get(k, k)
                r2 = m.get("r2")
                rmse = m.get("rmse")
                mae = m.get("mae")
                mrows.append(
                    [
                        Paragraph(label, body_style),
                        Paragraph(f"{r2:.4f}" if isinstance(r2, (int, float)) else "—", body_style),
                        Paragraph(f"{rmse:.4f}" if isinstance(rmse, (int, float)) else "—", body_style),
                        Paragraph(f"{mae:.4f}" if isinstance(mae, (int, float)) else "—", body_style),
                    ]
                )
            if len(mrows) > 1:
                mt = Table(mrows, colWidths=[doc.width * 0.28, doc.width * 0.24, doc.width * 0.24, doc.width * 0.24])
                mt.setStyle(
                    TableStyle(
                        [
                            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#BFDBFE")),
                            ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#1E3A8A")),
                            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#EFF6FF")]),
                            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#93C5FD")),
                            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                            ("LEFTPADDING", (0, 0), (-1, -1), 6),
                            ("TOPPADDING", (0, 0), (-1, -1), 4),
                            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                        ]
                    )
                )
                story.append(mt)
            story.append(Spacer(1, 0.15 * cm))

        recs = rep.get("recommendations") or []
        if recs:
            story.append(Paragraph("<b>老师的小建议</b>", body_style))
            for r in recs:
                story.append(Paragraph(f"• {html.escape(str(r))}", tip_style))

        story.append(Spacer(1, 0.35 * cm))
        if i < len(reports):
            story.append(
                Table(
                    [[""]],
                    colWidths=[doc.width],
                    style=TableStyle(
                        [
                            ("LINEABOVE", (0, 0), (-1, -1), 0.8, colors.HexColor("#E5E7EB")),
                        ]
                    ),
                )
            )
            story.append(Spacer(1, 0.25 * cm))

    story.append(Spacer(1, 0.3 * cm))
    story.append(
        Paragraph(
            "<i>—— 继续探索数据、训练模型，做小小 AI 科学家！——</i>",
            sub_style,
        )
    )

    doc.build(story)
    return buf.getvalue()
