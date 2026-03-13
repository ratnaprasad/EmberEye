from math import sin
from time import time as now_time

from PyQt5.QtCore import QRect, QRectF, Qt
from PyQt5.QtGui import QBrush, QColor, QFont, QLinearGradient, QPainterPath, QPen, QRadialGradient


def draw_fusion_overlay(widget, painter, width, height):
    """Render the fusion banner using the VideoWidget instance as context."""
    try:
        fusion = widget.fusion_data if isinstance(widget.fusion_data, dict) else {}

        mode_gain = 1.12 if bool(getattr(widget, "maximized", False)) else (0.92 if bool(getattr(widget, "is_minimized", False)) else 1.0)
        scale = min(width / 1280.0, height / 720.0) * mode_gain
        scale = max(0.74, min(scale, 1.28))

        confidence = float(fusion.get("confidence", 0.0) or 0.0)
        confidence = max(0.0, min(1.0, confidence))
        accuracy = int(confidence * 100)
        alarm = bool(fusion.get("alarm"))

        sources = set(fusion.get("sources", []) or [])
        thermal = float(fusion.get("thermal_max", 0.0) or 0.0)
        if thermal <= 0.0:
            try:
                last_matrix = getattr(widget, "_last_thermal_matrix", None)
                if last_matrix is not None:
                    import numpy as _np
                    arr = _np.array(last_matrix, dtype=float)
                    if arr.size > 0:
                        thermal = float(_np.max(arr))
            except Exception:
                pass
        gas = float(fusion.get("gas_ppm", 0.0) or 0.0)
        smoke = float(fusion.get("smoke_level", 0.0) or 0.0)
        flame_digital = int(fusion.get("flame_digital", 0) or 0)
        flame_analog_pct = float(fusion.get("flame_analog_pct", 0.0) or 0.0)
        flame_threshold_pct = 25.0
        flame_source_active = ("flame" in sources) or ("flame_analog" in sources) or ("flame_digital" in sources)
        flame_detected = bool(flame_digital == 1 or flame_analog_pct >= flame_threshold_pct)
        flame_confidence = max(1.0 if flame_digital == 1 else 0.0, max(0.0, min(1.0, flame_analog_pct / 100.0)))
        flame_conf_pct = int(flame_confidence * 100)
        hot_cells = int(len(fusion.get("hot_cells", []) or []))

        def metric_ratio(value, lo, hi):
            try:
                return max(0.0, min(1.0, (float(value) - float(lo)) / max(1e-6, (float(hi) - float(lo)))))
            except Exception:
                return 0.0

        def metric_severity(value, warn, crit, active=True):
            if not active:
                return 0
            try:
                value_f = float(value)
            except Exception:
                return 0
            if value_f >= float(crit):
                return 3
            if value_f >= float(warn):
                return 2
            return 1

        sev_thermal = metric_severity(thermal, 60.0, 75.0, "thermal" in sources)
        sev_gas = metric_severity(gas, 300.0, 500.0, "gas" in sources)
        sev_smoke = metric_severity(smoke, 30.0, 50.0, ("gas" in sources or "smoke" in sources))
        if flame_detected and flame_source_active:
            sev_flame = 3
        elif flame_source_active:
            sev_flame = 1
        else:
            sev_flame = 0
        sev_global = max(sev_thermal, sev_gas, sev_smoke, sev_flame, 1 if alarm else 0)

        # Naval / submarine tactical palette.
        _col_strip_lo = QColor(0x12, 0x14, 0x17, 224)
        _col_strip_hi = QColor(0x0E, 0x10, 0x14, 230)
        _col_card = QColor(0x1C, 0x1F, 0x26, 224)
        _col_accent = QColor(0xFF, 0xD2, 0x00)
        _col_value = QColor(0xFF, 0xD7, 0x00)
        _col_title = QColor(0xD2, 0xD8, 0xE0)
        _col_yellow_glow = QColor(0xFF, 0xD2, 0x00, 72)
        _col_sep = QColor(0xFF, 0xD2, 0x00, 153)
        _col_warn_red = QColor(0xFF, 0x00, 0x00)
        _col_flame_flash = QColor(0x44, 0x00, 0x00)

        def severity_color(sev):
            if sev >= 3:
                return _col_warn_red
            return _col_value

        def panel_accent(sev):
            if sev >= 3:
                return _col_warn_red
            return _col_accent

        def draw_card(rect, border_col):
            painter.fillRect(rect, _col_card)
            painter.setPen(QPen(_col_yellow_glow, 1))
            painter.drawRoundedRect(rect, max(7, int(8 * scale)), max(7, int(8 * scale)))
            painter.setPen(QPen(border_col, max(4, int(4 * scale)), Qt.SolidLine, Qt.RoundCap))
            painter.drawLine(rect.left() + 2, rect.top() + max(5, int(5 * scale)), rect.left() + 2, rect.bottom() - max(5, int(5 * scale)))

        def draw_glow_dot(cx, cy, color, radius):
            try:
                glow = QRadialGradient(cx, cy, radius * 1.8)
                glow.setColorAt(0.0, QColor(color.red(), color.green(), color.blue(), 196))
                glow.setColorAt(0.45, QColor(color.red(), color.green(), color.blue(), 70))
                glow.setColorAt(1.0, QColor(color.red(), color.green(), color.blue(), 0))
                painter.setBrush(QBrush(glow))
                painter.setPen(Qt.NoPen)
                painter.drawEllipse(QRectF(cx - radius * 1.6, cy - radius * 1.6, radius * 3.2, radius * 3.2))
            except Exception:
                pass
            painter.setBrush(color)
            painter.setPen(color)
            painter.drawEllipse(QRectF(cx - radius, cy - radius, radius * 2, radius * 2))

        def draw_alert_pulse(card_rect, sev):
            if sev < 2:
                return
            t = (sin(now_time() * 6.0) + 1.0) * 0.5
            if sev >= 3:
                pulse_alpha = int(52 + 82 * t)
                pulse_color = QColor(0x88, 0x00, 0x00, pulse_alpha)
            else:
                pulse_alpha = int(36 + 56 * t)
                pulse_color = QColor(0x7A, 0x54, 0x00, pulse_alpha)
            painter.fillRect(card_rect.adjusted(2, 2, -2, -2), pulse_color)

        def draw_shadow_text(rect, align, text, color, font):
            painter.setFont(font)
            painter.setPen(QColor(0, 0, 0, 164))
            painter.drawText(rect.adjusted(1, 1, 1, 1), align, text)
            painter.setPen(color)
            painter.drawText(rect, align, text)

        def draw_meter(rect, ratio, c1, c2=None, c3=None):
            painter.fillRect(rect, QColor(255, 215, 0, 32))
            r = max(0.0, min(1.0, float(ratio)))
            fill_w = int(rect.width() * r)
            if fill_w > 0:
                fill_rect = QRect(rect.x(), rect.y(), fill_w, rect.height())
                grad = QLinearGradient(fill_rect.left(), fill_rect.center().y(), fill_rect.right(), fill_rect.center().y())
                grad.setColorAt(0.0, c1)
                if c2 is not None and c3 is not None:
                    grad.setColorAt(0.5, c2)
                    grad.setColorAt(1.0, c3)
                else:
                    grad.setColorAt(1.0, c1)
                painter.fillRect(fill_rect, QBrush(grad))
            else:
                min_w = max(2, int(3 * scale))
                painter.fillRect(QRect(rect.x(), rect.y(), min_w, rect.height()), QColor(255, 215, 0, 88))
            painter.setPen(QPen(QColor(255, 210, 0, 150), 1))
            painter.drawRoundedRect(rect, int(3 * scale), int(3 * scale))

        drawer_rect, collapsed = widget._fusion_drawer_rect_for_layout()
        collapsed = bool(getattr(widget, "fusion_drawer_collapsed", False))

        if collapsed:
            rail = drawer_rect
            rail_path = QPainterPath()
            rail_path.addRoundedRect(QRectF(rail), max(7, int(9 * scale)), max(7, int(9 * scale)))
            rail_grad = QLinearGradient(rail.left(), rail.top(), rail.right(), rail.bottom())
            rail_grad.setColorAt(0.0, QColor(26, 31, 40, 236))
            rail_grad.setColorAt(1.0, QColor(17, 20, 28, 230))
            painter.fillPath(rail_path, QBrush(rail_grad))
            painter.setPen(QPen(QColor(245, 247, 250, 56), 1))
            painter.drawPath(rail_path)
            status_col = severity_color(sev_global)
            dot_r = max(3, int(4 * scale))
            dot_x = rail.x() + int(8 * scale)
            dot_y = rail.center().y() - dot_r
            painter.setPen(status_col)
            painter.setBrush(status_col)
            painter.drawEllipse(dot_x, dot_y, dot_r * 2, dot_r * 2)
            draw_shadow_text(
                QRect(rail.x() + int(16 * scale), rail.y(), rail.width() - int(20 * scale), rail.height()),
                Qt.AlignVCenter | Qt.AlignLeft,
                f"FUSION BOARD  {accuracy}%",
                QColor(245, 245, 245),
                QFont("Arial", max(8, int(10 * scale)), QFont.Bold),
            )
            return

        strip = drawer_rect
        strip_path = QPainterPath()
        strip_radius = max(8, int(10 * scale))
        strip_path.addRoundedRect(QRectF(strip), strip_radius, strip_radius)
        strip_grad = QLinearGradient(strip.left(), strip.top(), strip.right(), strip.bottom())
        strip_grad.setColorAt(0.0, _col_strip_lo)
        strip_grad.setColorAt(1.0, _col_strip_hi)
        painter.fillPath(strip_path, QBrush(strip_grad))
        painter.setPen(QPen(QColor(255, 255, 255, 34), 1))
        painter.drawPath(strip_path)

        card_gap = max(1, int(1 * scale))
        inner = strip.adjusted(int(6 * scale), int(6 * scale), -int(6 * scale), -int(6 * scale))
        card_h = max(54, inner.height())

        cards = [
            ("global", "◉", "PREDICTION ACCURACY %"),
            ("thermal", "🌡", "THERMAL"),
            ("gas", "⌘", "GAS"),
            ("smoke", "☁", "SMOKE"),
            ("flame", "🔥", "FLAME"),
            ("action", "⚡", "ACTION"),
        ]
        preferred_w = {
            "global": int(258 * scale),
            "thermal": int(168 * scale),
            "gas": int(166 * scale),
            "smoke": int(166 * scale),
            "flame": int(196 * scale),
            "action": int(150 * scale),
        }

        card_by_key = {k: (k, icon, title) for k, icon, title in cards}
        ordered_sets = [
            ["global", "thermal", "gas", "smoke", "flame", "action"],
            ["global", "thermal", "gas", "flame", "action"],
            ["global", "thermal", "gas", "flame"],
            ["global", "thermal", "gas"],
            ["global", "thermal"],
            ["global"],
        ]
        visible_keys = ordered_sets[-1]
        min_stretch = 0.66
        for candidate in ordered_sets:
            need = sum(preferred_w[k] for k in candidate) + (card_gap * (len(candidate) - 1))
            if need <= int(inner.width() / min_stretch):
                visible_keys = candidate
                break

        visible_cards = [card_by_key[k] for k in visible_keys]
        total_pref = sum(preferred_w[k] for k in visible_keys) + (card_gap * (len(visible_keys) - 1))
        stretch = max(0.66, min(1.0, inner.width() / max(1, total_pref)))
        widget._action_card_rect = None

        x = inner.x()
        for idx, (key, icon, title) in enumerate(visible_cards):
            cw = int(preferred_w[key] * stretch)
            if idx == len(visible_cards) - 1:
                cw = max(cw, inner.right() - x + 1)
            card = QRect(x, inner.y(), cw, card_h)
            x += cw + card_gap

            severity = 1
            if key == "global":
                severity = sev_global
            elif key == "thermal":
                severity = max(1, sev_thermal)
            elif key == "gas":
                severity = max(1, sev_gas)
            elif key == "smoke":
                severity = max(1, sev_smoke)
            elif key == "flame":
                severity = max(1, sev_flame)
            elif key == "action":
                severity = max(1, 3 if widget.alarm_active else 1)

            draw_card(card, panel_accent(severity if key == "global" else 1))

            if idx < len(visible_cards) - 1:
                painter.setPen(QPen(_col_sep, 1))
                painter.drawLine(card.right(), card.top() + int(7 * scale), card.right(), card.bottom() - int(7 * scale))

            title_font = QFont("Roboto Mono", max(11, int(12 * scale)), QFont.Bold)
            value_font = QFont("Roboto Mono", max(16, int(20 * scale)), QFont.Bold)
            small_font = QFont("Roboto Mono", max(10, int(11 * scale)))
            if value_font.family() == "":
                value_font = QFont("JetBrains Mono", max(16, int(20 * scale)), QFont.Bold)
            value_col = _col_value

            draw_shadow_text(
                card.adjusted(int(8 * scale), int(2 * scale), -int(6 * scale), 0),
                Qt.AlignLeft | Qt.AlignTop,
                f"{icon} {title}".strip(),
                _col_title,
                title_font,
            )

            if key == "global":
                ring_cx = card.left() + int(54 * scale)
                ring_cy = card.top() + int(54 * scale)
                outer_r = max(18, int(24 * scale))
                mid_r = max(14, int(19 * scale))
                inner_r = max(10, int(14 * scale))
                base = max(0.0, min(1.0, confidence))

                painter.setBrush(Qt.NoBrush)
                low_conf = accuracy < 70
                if low_conf:
                    ring_spec = [
                        (outer_r, QColor(0xFF, 0xBF, 0x00), 0.78),
                        (mid_r, QColor(0xFF, 0xBF, 0x00), 0.62),
                        (inner_r, QColor(0xFF, 0xBF, 0x00), 0.46),
                    ]
                else:
                    ring_spec = [
                        (outer_r, QColor(0xFF, 0xD7, 0x00), base),
                        (mid_r, QColor(0xFF, 0xC8, 0x00), min(1.0, base * 0.92)),
                        (inner_r, QColor(0xCC, 0xA8, 0x00), min(1.0, base * 0.84)),
                    ]
                for rr, col, frac in ring_spec:
                    painter.setPen(QPen(QColor(255, 255, 255, 44), max(1, int(1 * scale))))
                    painter.drawArc(QRectF(ring_cx - rr, ring_cy - rr, rr * 2, rr * 2), 0, 360 * 16)
                    painter.setPen(QPen(col, max(3, int(4 * scale)), Qt.SolidLine, Qt.RoundCap))
                    painter.drawArc(QRectF(ring_cx - rr, ring_cy - rr, rr * 2, rr * 2), 90 * 16, int(-360 * 16 * frac))

                draw_shadow_text(
                    card.adjusted(int(78 * scale), int(36 * scale), -int(10 * scale), 0),
                    Qt.AlignLeft | Qt.AlignTop,
                    f"PREDICTION: {confidence * 100.0:.1f}%",
                    value_col,
                    QFont("Roboto Mono", max(11, int(12 * scale)), QFont.Bold),
                )
                conf_label = "RELIABILITY: UNRELIABLE" if low_conf else ("RELIABILITY: HIGH" if accuracy >= 90 else "RELIABILITY: TRACKING")
                draw_shadow_text(
                    card.adjusted(int(78 * scale), int(56 * scale), -int(10 * scale), 0),
                    Qt.AlignLeft | Qt.AlignTop,
                    conf_label,
                    _col_title,
                    QFont("Roboto Mono", max(10, int(11 * scale)), QFont.Bold),
                )
                draw_glow_dot(card.right() - int(12 * scale), card.center().y() + int(4 * scale), _col_value, max(4, int(5 * scale)))

            elif key == "thermal":
                draw_alert_pulse(card, sev_thermal)
                draw_shadow_text(card.adjusted(int(8 * scale), int(26 * scale), -int(8 * scale), 0), Qt.AlignHCenter | Qt.AlignTop, f"{thermal:.1f}°C", value_col, value_font)
                draw_meter(
                    QRect(card.left() + int(8 * scale), card.bottom() - int(19 * scale), card.width() - int(16 * scale), max(4, int(5 * scale))),
                    metric_ratio(thermal, 0.0, 100.0),
                    QColor(255, 180, 76),
                    QColor(255, 196, 92),
                    QColor(255, 214, 126),
                )
                therm_state = "OP-READY" if thermal < 60.0 else "ELEVATED"
                draw_shadow_text(card.adjusted(int(8 * scale), int(54 * scale), 0, 0), Qt.AlignLeft | Qt.AlignTop, therm_state, _col_title, small_font)

            elif key == "gas":
                draw_alert_pulse(card, sev_gas)
                draw_shadow_text(card.adjusted(int(8 * scale), int(26 * scale), -int(8 * scale), 0), Qt.AlignHCenter | Qt.AlignTop, f"{int(gas)} PPM", value_col, value_font)
                draw_meter(
                    QRect(card.left() + int(8 * scale), card.bottom() - int(20 * scale), card.width() - int(16 * scale), max(6, int(7 * scale))),
                    metric_ratio(gas, 0.0, 1500.0),
                    QColor(255, 176, 70),
                    QColor(255, 194, 90),
                    QColor(255, 214, 124),
                )
                gas_badge = "NOMINAL" if gas < 400 else "WARNING"
                gas_col = _col_value if gas < 400 else _col_warn_red
                draw_shadow_text(card.adjusted(int(8 * scale), int(54 * scale), 0, 0), Qt.AlignLeft | Qt.AlignTop, gas_badge, gas_col, QFont("Roboto Mono", max(11, int(11 * scale)), QFont.Bold))

            elif key == "smoke":
                draw_alert_pulse(card, sev_smoke)
                draw_shadow_text(card.adjusted(int(8 * scale), int(26 * scale), -int(8 * scale), 0), Qt.AlignHCenter | Qt.AlignTop, f"{int(smoke)}%", value_col, value_font)
                draw_meter(
                    QRect(card.left() + int(8 * scale), card.bottom() - int(20 * scale), card.width() - int(16 * scale), max(4, int(5 * scale))),
                    metric_ratio(smoke, 0.0, 100.0),
                    QColor(255, 196, 64),
                    QColor(255, 208, 88),
                    QColor(255, 221, 120),
                )
                tick_x = card.left() + int(8 * scale) + int((card.width() - int(16 * scale)) * 0.5)
                tick_y = card.bottom() - int(20 * scale)
                painter.setPen(QPen(QColor(255, 245, 138), max(1, int(1 * scale))))
                painter.drawLine(tick_x, tick_y - int(5 * scale), tick_x, tick_y + int(7 * scale))
                draw_shadow_text(card.adjusted(int(8 * scale), int(54 * scale), 0, 0), Qt.AlignLeft | Qt.AlignTop, "WARN @ 50%", _col_title, small_font)

            elif key == "flame":
                if flame_detected:
                    pulse_alpha = int(90 + 90 * ((sin(now_time() * 8.0) + 1.0) * 0.5))
                    painter.fillRect(card.adjusted(2, 2, -2, -2), QColor(_col_flame_flash.red(), _col_flame_flash.green(), _col_flame_flash.blue(), pulse_alpha))
                badge_w = int(card.width() * 0.80)
                badge_h = max(16, int(28 * scale))
                badge = QRect(card.center().x() - int(badge_w / 2), card.top() + int(26 * scale), badge_w, badge_h)
                badge_col = _col_warn_red if flame_detected else _col_accent
                if flame_detected:
                    glow = QRadialGradient(badge.center().x(), badge.center().y(), badge_w * 0.55)
                    glow.setColorAt(0.0, QColor(255, 0, 0, 92))
                    glow.setColorAt(1.0, QColor(255, 48, 48, 0))
                    painter.fillRect(badge.adjusted(-6, -4, 6, 4), QBrush(glow))
                painter.fillRect(badge, QColor(18, 18, 18, 132))
                painter.setPen(QPen(badge_col, max(1, int(2 * scale))))
                painter.drawRoundedRect(badge, int(6 * scale), int(6 * scale))
                clear_text_col = QColor(0x22, 0x28, 0x32) if not flame_detected else QColor(250, 250, 250)
                draw_shadow_text(badge, Qt.AlignCenter, "DETECTED" if flame_detected else "CLEAR", clear_text_col, QFont("Arial", max(11, int(12 * scale)), QFont.Bold))
                draw_shadow_text(card.adjusted(int(8 * scale), int(56 * scale), -int(8 * scale), 0), Qt.AlignHCenter | Qt.AlignTop, f"Flame: {flame_conf_pct}%", value_col, QFont("Roboto Mono", max(11, int(11 * scale)), QFont.Bold))
                draw_shadow_text(card.adjusted(int(8 * scale), int(70 * scale), -int(8 * scale), 0), Qt.AlignHCenter | Qt.AlignTop, f"A:{flame_analog_pct:.1f}% D:{flame_digital}", _col_title, QFont("Roboto Mono", max(9, int(10 * scale)), QFont.Bold))
                draw_glow_dot(card.right() - int(14 * scale), card.top() + int(12 * scale), badge_col if flame_detected else _col_value, max(3, int(4 * scale)))

            elif key == "action":
                widget._action_card_rect = QRect(card)
                draw_shadow_text(card.adjusted(int(8 * scale), int(18 * scale), 0, 0), Qt.AlignLeft | Qt.AlignTop, "Actions:", _col_title, small_font)
                draw_glow_dot(card.right() - int(12 * scale), card.top() + int(12 * scale), _col_accent, max(3, int(4 * scale)))

                slot_w = card.width() - int(16 * scale)
                slot_h = max(14, int(18 * scale))
                slot_x = card.x() + int(8 * scale)
                top_slot = QRect(slot_x, card.y() + int(30 * scale), slot_w, slot_h)
                painter.fillRect(top_slot, QColor(0x32, 0x3A, 0x46, 200))
                painter.setPen(QPen(QColor(0xFF, 0xD2, 0x00, 180), 1))
                painter.drawRoundedRect(top_slot, int(6 * scale), int(6 * scale))
                draw_shadow_text(top_slot, Qt.AlignCenter, "SECURE", _col_value, QFont("Roboto Mono", max(10, int(11 * scale)), QFont.Bold))

        widget._position_action_controls()

        if len(visible_cards) < len(cards):
            draw_shadow_text(
                QRect(strip.right() - int(20 * scale), strip.top() + int(2 * scale), int(16 * scale), int(12 * scale)),
                Qt.AlignCenter,
                "...",
                QColor(220, 230, 240),
                QFont("Arial", max(8, int(10 * scale)), QFont.Bold),
            )

    except Exception as e:
        print(f"Fusion overlay draw error: {e}")
