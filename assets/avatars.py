"""内置全套高清儿童绘本风卡通立绘（纯 SVG，零外部图片依赖）。

所有立绘由参数化 SVG 生成：同一套身体 + 四档情绪表情
（normal 如常 / surprised 吃惊 / nervous 心虚流汗 / confess 招供大哭），
保证角色一致性的同时，让对话情绪"活"起来。
输出既可直接 st.markdown 内联，也可转 base64 data URI。
"""

from __future__ import annotations

import base64
from typing import Dict

from agents.characters import MOOD_CONFESS, MOOD_NERVOUS, MOOD_NORMAL, MOOD_SURPRISED

PALETTE: Dict[str, str] = {
    "ink": "#4A3B32",
    "blush": "#FFB3C1",
    "white": "#FFFFFF",
    "sparky_body": "#FFE9A8",
    "sparky_wing": "#BDE3FF",
    "sparky_beak": "#FFA94D",
    "pan_skin": "#FFE0C4",
    "pan_hair": "#6B4A34",
    "pan_shirt": "#FFB74D",
    "pan_pants": "#7EC8A0",
    "zhou_skin": "#FFE3D0",
    "zhou_hair": "#5A4632",
    "zhou_dress": "#7CC7F5",
    "zhou_collar": "#FFFFFF",
    "zhang_skin": "#F6D9BE",
    "zhang_hair": "#E8E8E8",
    "zhang_coat": "#C9A87C",
    "zhang_hat": "#8FBF9F",
}

MOODS = (MOOD_NORMAL, MOOD_SURPRISED, MOOD_NERVOUS, MOOD_CONFESS)


def _svg_wrap(inner: str, size: int = 220, viewBox: str = "0 0 240 240") -> str:
    return (
        f'<svg viewBox="{viewBox}" width="{size}" height="{size}" xmlns="http://www.w3.org/2000/svg" '
        f'role="img" style="display:block;margin:0 auto;overflow:visible">'
        f'<defs><filter id="soft" x="-30%" y="-30%" width="160%" height="160%">'
        f'<feDropShadow dx="0" dy="4" stdDeviation="4" flood-color="#C9B79A" flood-opacity="0.35"/>'
        f"</filter></defs>{inner}</svg>"
    )


def _eyes(cx_left: int, cx_right: int, cy: int, mood: str, r: int = 7, color: str = None) -> str:
    """四档情绪的眼睛 + 眉毛。"""
    color = color or PALETTE["ink"]
    if mood == MOOD_NORMAL:
        return (
            f'<circle cx="{cx_left}" cy="{cy}" r="{r}" fill="{color}"/>'
            f'<circle cx="{cx_right}" cy="{cy}" r="{r}" fill="{color}"/>'
            f'<circle cx="{cx_left + 2.5}" cy="{cy - 2.5}" r="2.4" fill="#fff"/>'
            f'<circle cx="{cx_right + 2.5}" cy="{cy - 2.5}" r="2.4" fill="#fff"/>'
        )
    if mood == MOOD_SURPRISED:
        return (
            f'<circle cx="{cx_left}" cy="{cy}" r="{r + 3}" fill="#fff" stroke="{color}" stroke-width="2.4"/>'
            f'<circle cx="{cx_right}" cy="{cy}" r="{r + 3}" fill="#fff" stroke="{color}" stroke-width="2.4"/>'
            f'<circle cx="{cx_left}" cy="{cy}" r="{r - 1}" fill="{color}"/>'
            f'<circle cx="{cx_right}" cy="{cy}" r="{r - 1}" fill="{color}"/>'
            f'<path d="M{cx_left - 9} {cy - 17} q9 -7 18 -1" stroke="{color}" stroke-width="3" fill="none" stroke-linecap="round"/>'
            f'<path d="M{cx_right - 9} {cy - 18} q9 -6 18 0" stroke="{color}" stroke-width="3" fill="none" stroke-linecap="round"/>'
        )
    if mood == MOOD_NERVOUS:
        return (
            f'<path d="M{cx_left - 8} {cy + 2} q8 -11 16 0" stroke="{color}" stroke-width="3.4" fill="none" stroke-linecap="round"/>'
            f'<path d="M{cx_right - 8} {cy + 2} q8 -11 16 0" stroke="{color}" stroke-width="3.4" fill="none" stroke-linecap="round"/>'
            f'<path d="M{cx_left - 9} {cy - 13} l16 4" stroke="{color}" stroke-width="3" stroke-linecap="round"/>'
            f'<path d="M{cx_right + 9} {cy - 13} l-16 4" stroke="{color}" stroke-width="3" stroke-linecap="round"/>'
        )
    return (
        f'<path d="M{cx_left - 9} {cy - 3} q9 10 18 0" stroke="{color}" stroke-width="3.6" fill="none" stroke-linecap="round"/>'
        f'<path d="M{cx_right - 9} {cy - 3} q9 10 18 0" stroke="{color}" stroke-width="3.6" fill="none" stroke-linecap="round"/>'
        f'<path d="M{cx_left - 10} {cy - 14} l18 6" stroke="{color}" stroke-width="3" stroke-linecap="round"/>'
        f'<path d="M{cx_right + 10} {cy - 14} l-18 6" stroke="{color}" stroke-width="3" stroke-linecap="round"/>'
    )


def _mouth(cx: int, cy: int, mood: str, width: int = 16) -> str:
    ink = PALETTE["ink"]
    if mood == MOOD_NORMAL:
        return f'<path d="M{cx - width} {cy} q{width} {width + 4} {width * 2} 0" stroke="{ink}" stroke-width="3.2" fill="none" stroke-linecap="round"/>'
    if mood == MOOD_SURPRISED:
        return f'<ellipse cx="{cx}" cy="{cy + 3}" rx="7" ry="9" fill="#8C5A4A"/>'
    if mood == MOOD_NERVOUS:
        return f'<path d="M{cx - width} {cy + 3} q{width / 2} -7 {width} 0 q{width / 2} 7 {width} 0" stroke="{ink}" stroke-width="3" fill="none" stroke-linecap="round"/>'
    return f'<path d="M{cx - width} {cy + 7} q{width} -{width + 2} {width * 2} 0" stroke="{ink}" stroke-width="3.4" fill="#B4553F" stroke-linecap="round"/>'


def _blush(cx_left: int, cx_right: int, cy: int, opacity: float = 0.75) -> str:
    blush = PALETTE["blush"]
    return (
        f'<ellipse cx="{cx_left}" cy="{cy}" rx="11" ry="7" fill="{blush}" opacity="{opacity}"/>'
        f'<ellipse cx="{cx_right}" cy="{cy}" rx="11" ry="7" fill="{blush}" opacity="{opacity}"/>'
    )


def _sweat(x: int, y: int) -> str:
    return f'<path d="M{x} {y} q-7 11 0 15 q7 -4 0 -15" fill="#8ED8F8" stroke="#5BB8E0" stroke-width="1.4"/>'


def _tear(x: int, y: int) -> str:
    return (
        f'<path d="M{x} {y} q-8 14 0 19 q8 -5 0 -19" fill="#7FD3FF" stroke="#4FB3E8" stroke-width="1.5">'
        f'<animateTransform attributeName="transform" type="translate" values="0 0; 0 10; 0 0" '
        f'dur="1.4s" repeatCount="indefinite"/></path>'
    )


def _sparkles(color: str = "#FFD166") -> str:
    points = [(34, 46), (206, 58), (28, 168), (212, 158)]
    out = ""
    for i, (x, y) in enumerate(points):
        out += (
            f'<path d="M{x} {y - 8} l2.6 5.4 l5.4 2.6 l-5.4 2.6 l-2.6 5.4 l-2.6 -5.4 l-5.4 -2.6 l5.4 -2.6 z" '
            f'fill="{color}" opacity="0.9"><animate attributeName="opacity" values="0.25;1;0.25" '
            f'dur="{1.6 + i * 0.3}s" repeatCount="indefinite"/></path>'
        )
    return out


# ---------------------------------------------------------------- 鸡飞飞
def sparky_svg(mood: str = MOOD_NORMAL, size: int = 190, label: str = "") -> str:
    """羽毛球型外星萌宠：圆脑袋 + 羽毛球裙摆 + 小翅膀 + 头顶小螺旋桨。"""
    p = PALETTE
    body = (
        f'<ellipse cx="120" cy="196" rx="52" ry="12" fill="#E7DCC6" opacity="0.7"/>'
        f'<path d="M78 150 L162 150 L146 206 Q120 216 94 206 Z" fill="{p["sparky_wing"]}" '
        f'stroke="#8FC7E8" stroke-width="3" stroke-linejoin="round"/>'
        f'<path d="M96 152 L104 204 M120 152 L120 210 M144 152 L136 204" stroke="#8FC7E8" '
        f'stroke-width="2.4" stroke-linecap="round"/>'
        f'<ellipse cx="120" cy="112" rx="62" ry="58" fill="{p["sparky_body"]}" filter="url(#soft)"/>'
        f'<ellipse cx="120" cy="112" rx="62" ry="58" fill="none" stroke="#EBC97F" stroke-width="3"/>'
        f'<path d="M58 108 q-26 6 -22 30 q20 6 30 -12 z" fill="{p["sparky_wing"]}" stroke="#8FC7E8" stroke-width="2.6"/>'
        f'<path d="M182 108 q26 6 22 30 q-20 6 -30 -12 z" fill="{p["sparky_wing"]}" stroke="#8FC7E8" stroke-width="2.6"/>'
        f'<path d="M120 54 q4 -18 16 -22" stroke="#E9B949" stroke-width="3.4" fill="none" stroke-linecap="round"/>'
        f'<g transform="translate(138,30)"><animateTransform attributeName="transform" type="rotate" '
        f'from="0" to="360" dur="1.6s" repeatCount="indefinite" additive="sum"/>'
        f'<ellipse cx="0" cy="0" rx="20" ry="5" fill="#FF8FA3" opacity="0.9"/></g>'
        f'<circle cx="138" cy="30" r="4.5" fill="#FF6B8A"/>'
        f'{_blush(88, 152, 130)}'
        f'<path d="M110 136 q10 9 20 0" stroke="{p["ink"]}" stroke-width="3" fill="none" stroke-linecap="round"/>'
        f'{_eyes(98, 142, 112, mood, r=8)}'
        f'<rect x="104" y="150" width="32" height="18" rx="6" fill="#7EC8A0" stroke="#5FAF85" stroke-width="2"/>'
        f'<text x="120" y="163" font-size="10" text-anchor="middle" fill="#fff" '
        f'font-family="system-ui, sans-serif" font-weight="700">SPARK</text>'
        f"{_sparkles()}"
    )
    extras = ""
    if mood == MOOD_NERVOUS:
        extras = _sweat(176, 78) + _sweat(60, 92)
    elif mood == MOOD_CONFESS:
        extras = _tear(96, 122) + _tear(146, 122)
    elif mood == MOOD_SURPRISED:
        extras = f'<text x="186" y="66" font-size="26" fill="#FF8FA3" font-family="system-ui">！</text>'
    caption = (
        f'<text x="120" y="234" font-size="15" text-anchor="middle" fill="#7A6A55" '
        f'font-family="system-ui, sans-serif" font-weight="700">{label}</text>'
        if label
        else ""
    )
    return _svg_wrap(body + extras + caption, size)


# ---------------------------------------------------------------- 潘小达
def pan_svg(mood: str = MOOD_NORMAL, size: int = 220) -> str:
    p = PALETTE
    inner = (
        f'<ellipse cx="120" cy="222" rx="62" ry="11" fill="#E7DCC6" opacity="0.7"/>'
        f'<rect x="94" y="186" width="20" height="30" rx="9" fill="{p["pan_pants"]}"/>'
        f'<rect x="126" y="186" width="20" height="30" rx="9" fill="{p["pan_pants"]}"/>'
        f'<ellipse cx="104" cy="218" rx="15" ry="8" fill="#6B7C93"/>'
        f'<ellipse cx="136" cy="218" rx="15" ry="8" fill="#6B7C93"/>'
        f'<ellipse cx="120" cy="160" rx="58" ry="48" fill="{p["pan_shirt"]}" stroke="#E39A34" stroke-width="3" filter="url(#soft)"/>'
        f'<path d="M66 150 q54 16 108 0" stroke="#FFD79A" stroke-width="7" fill="none"/>'
        f'<path d="M68 172 q52 14 104 0" stroke="#FFD79A" stroke-width="7" fill="none"/>'
        f'<ellipse cx="64" cy="158" rx="13" ry="22" fill="{p["pan_shirt"]}" stroke="#E39A34" stroke-width="2.6"/>'
        f'<ellipse cx="176" cy="152" rx="13" ry="22" fill="{p["pan_shirt"]}" stroke="#E39A34" stroke-width="2.6"/>'
        f'<circle cx="62" cy="178" r="10" fill="{p["pan_skin"]}"/>'
        f'<rect x="150" y="164" width="42" height="34" rx="8" fill="#FF8FA3" stroke="#E76F8A" stroke-width="2.4"/>'
        f'<path d="M150 172 h42" stroke="#E76F8A" stroke-width="2"/>'
        f'<text x="171" y="192" font-size="13" text-anchor="middle" fill="#fff" font-family="system-ui" font-weight="700">零食</text>'
        f'<circle cx="120" cy="88" r="52" fill="{p["pan_skin"]}" stroke="#E9BE9C" stroke-width="3"/>'
        f'<path d="M70 82 q10 -46 50 -46 q42 0 50 44 q-16 -18 -30 -14 q-6 -14 -22 -12 q-18 2 -22 14 q-14 -2 -26 14 z" fill="{p["pan_hair"]}"/>'
        f'<circle cx="68" cy="92" r="9" fill="{p["pan_skin"]}" stroke="#E9BE9C" stroke-width="2"/>'
        f'<circle cx="172" cy="92" r="9" fill="{p["pan_skin"]}" stroke="#E9BE9C" stroke-width="2"/>'
        f'<circle cx="140" cy="112" r="2.2" fill="#8C5A4A"/>'
        f"{_blush(92, 148, 104)}"
        f"{_eyes(102, 138, 90, mood, r=7)}"
        f"{_mouth(120, 116, mood, width=15)}"
    )
    extras = ""
    if mood == MOOD_NERVOUS:
        extras = _sweat(178, 62) + _sweat(60, 70)
    elif mood == MOOD_CONFESS:
        extras = _tear(100, 100) + _tear(140, 100)
    return _svg_wrap(inner + extras, size)


# ---------------------------------------------------------------- 周晓晓
def zhou_svg(mood: str = MOOD_NORMAL, size: int = 220) -> str:
    p = PALETTE
    inner = (
        f'<ellipse cx="120" cy="222" rx="58" ry="11" fill="#E7DCC6" opacity="0.7"/>'
        f'<rect x="100" y="190" width="16" height="26" rx="8" fill="#FFE3D0"/>'
        f'<rect x="124" y="190" width="16" height="26" rx="8" fill="#FFE3D0"/>'
        f'<ellipse cx="108" cy="217" rx="13" ry="7" fill="#E76F8A"/>'
        f'<ellipse cx="132" cy="217" rx="13" ry="7" fill="#E76F8A"/>'
        f'<path d="M120 128 L76 196 Q120 208 164 196 Z" fill="{p["zhou_dress"]}" stroke="#5BAEDD" stroke-width="3" stroke-linejoin="round"/>'
        f'<path d="M92 172 q28 10 56 0" stroke="#BDE3FF" stroke-width="6" fill="none"/>'
        f'<path d="M106 130 l14 12 l14 -12 z" fill="{p["zhou_collar"]}" stroke="#DCEBF5" stroke-width="2"/>'
        f'<ellipse cx="76" cy="150" rx="11" ry="20" fill="{p["zhou_dress"]}" stroke="#5BAEDD" stroke-width="2.4"/>'
        f'<ellipse cx="164" cy="150" rx="11" ry="20" fill="{p["zhou_dress"]}" stroke="#5BAEDD" stroke-width="2.4"/>'
        f'<circle cx="74" cy="168" r="9" fill="{p["zhou_skin"]}"/>'
        f'<circle cx="166" cy="168" r="9" fill="{p["zhou_skin"]}"/>'
        f'<circle cx="120" cy="84" r="48" fill="{p["zhou_skin"]}" stroke="#EFC7AE" stroke-width="3"/>'
        f'<path d="M72 78 q6 -44 48 -44 q42 0 48 44 q-14 -20 -30 -18 q-8 -12 -18 -12 q-12 0 -18 12 q-16 -2 -30 18 z" fill="{p["zhou_hair"]}"/>'
        f'<ellipse cx="62" cy="104" rx="13" ry="26" fill="{p["zhou_hair"]}"/>'
        f'<ellipse cx="178" cy="104" rx="13" ry="26" fill="{p["zhou_hair"]}"/>'
        f'<circle cx="62" cy="80" r="6" fill="#FF8FA3"/><circle cx="178" cy="80" r="6" fill="#FF8FA3"/>'
        f"{_blush(94, 146, 100)}"
        f"{_eyes(103, 137, 86, mood, r=6.5)}"
        f'<circle cx="103" cy="86" r="16" fill="none" stroke="#4A6B8A" stroke-width="3.2"/>'
        f'<circle cx="137" cy="86" r="16" fill="none" stroke="#4A6B8A" stroke-width="3.2"/>'
        f'<path d="M119 86 h2 M87 84 q-8 -2 -12 3 M153 84 q8 -2 12 3" stroke="#4A6B8A" stroke-width="3" fill="none" stroke-linecap="round"/>'
        f"{_mouth(120, 112, mood, width=13)}"
        f'<rect x="150" y="140" width="30" height="14" rx="4" fill="#FFD166" stroke="#E3B341" stroke-width="1.8"/>'
        f'<text x="165" y="151" font-size="9" text-anchor="middle" fill="#7A5B18" font-family="system-ui" font-weight="700">科学</text>'
    )
    extras = ""
    if mood == MOOD_NERVOUS:
        extras = _sweat(172, 58)
    elif mood == MOOD_CONFESS:
        extras = _tear(101, 96) + _tear(139, 96)
    return _svg_wrap(inner + extras, size)


# ---------------------------------------------------------------- 张爷爷
def zhang_svg(mood: str = MOOD_NORMAL, size: int = 220) -> str:
    p = PALETTE
    inner = (
        f'<ellipse cx="120" cy="222" rx="60" ry="11" fill="#E7DCC6" opacity="0.7"/>'
        f'<rect x="98" y="188" width="18" height="28" rx="8" fill="#7C6A57"/>'
        f'<rect x="124" y="188" width="18" height="28" rx="8" fill="#7C6A57"/>'
        f'<ellipse cx="107" cy="217" rx="14" ry="7" fill="#5B4B3C"/>'
        f'<ellipse cx="133" cy="217" rx="14" ry="7" fill="#5B4B3C"/>'
        f'<path d="M120 126 L74 196 Q120 208 166 196 Z" fill="{p["zhang_coat"]}" stroke="#A9885F" stroke-width="3" stroke-linejoin="round"/>'
        f'<rect x="132" y="160" width="26" height="20" rx="5" fill="#B8946A" stroke="#A9885F" stroke-width="2"/>'
        f'<path d="M120 128 v62" stroke="#A9885F" stroke-width="2.4"/>'
        f'<circle cx="120" cy="146" r="3" fill="#7A5B34"/><circle cx="120" cy="164" r="3" fill="#7A5B34"/>'
        f'<ellipse cx="74" cy="152" rx="11" ry="21" fill="{p["zhang_coat"]}" stroke="#A9885F" stroke-width="2.4"/>'
        f'<ellipse cx="166" cy="146" rx="11" ry="20" fill="{p["zhang_coat"]}" stroke="#A9885F" stroke-width="2.4"/>'
        f'<circle cx="72" cy="170" r="9" fill="{p["zhang_skin"]}"/>'
        f'<circle cx="168" cy="128" r="9" fill="{p["zhang_skin"]}"/>'
        f'<circle cx="120" cy="84" r="46" fill="{p["zhang_skin"]}" stroke="#E0BE9E" stroke-width="3"/>'
        f'<path d="M76 66 q44 -34 88 0 q-44 -12 -88 0 z" fill="{p["zhang_hat"]}" stroke="#6FA183" stroke-width="2.6"/>'
        f'<rect x="74" y="62" width="92" height="10" rx="5" fill="#6FA183"/>'
        f'<path d="M92 96 q28 40 56 0 q-6 34 -28 34 q-22 0 -28 -34 z" fill="{p["zhang_hair"]}" stroke="#CFCFCF" stroke-width="2"/>'
        f'<path d="M88 74 q12 -8 24 -2 M128 72 q12 -6 24 2" stroke="{p["zhang_hair"]}" stroke-width="6" fill="none" stroke-linecap="round"/>'
        f'<circle cx="74" cy="90" r="8" fill="{p["zhang_skin"]}" stroke="#E0BE9E" stroke-width="2"/>'
        f'<circle cx="166" cy="90" r="8" fill="{p["zhang_skin"]}" stroke="#E0BE9E" stroke-width="2"/>'
        f"{_blush(94, 146, 96, opacity=0.55)}"
        f"{_eyes(104, 136, 86, mood, r=6)}"
        f'<circle cx="104" cy="88" r="14" fill="none" stroke="#8A6E4F" stroke-width="2.6"/>'
        f'<circle cx="136" cy="88" r="14" fill="none" stroke="#8A6E4F" stroke-width="2.6"/>'
        f'<path d="M118 88 h4 M90 92 q-8 2 -10 8 M150 92 q8 2 10 8" stroke="#8A6E4F" stroke-width="2.4" fill="none" stroke-linecap="round"/>'
        f"{_mouth(120, 108, mood, width=12)}"
        f'<circle cx="104" cy="206" r="1.8" fill="#fff"/><circle cx="112" cy="210" r="1.6" fill="#fff"/>'
        f'<circle cx="130" cy="208" r="1.8" fill="#fff"/>'
    )
    extras = ""
    if mood == MOOD_NERVOUS:
        extras = _sweat(176, 66)
    elif mood == MOOD_CONFESS:
        extras = _tear(102, 98) + _tear(138, 98)
    return _svg_wrap(inner + extras, size)


AVATAR_BUILDERS = {"sparky": sparky_svg, "pan": pan_svg, "zhou": zhou_svg, "zhang": zhang_svg}


def avatar_svg(who: str, mood: str = MOOD_NORMAL, size: int = 220) -> str:
    """统一入口：`avatar_svg('pan', 'nervous')`。未知角色回落到鸡飞飞。"""
    builder = AVATAR_BUILDERS.get(who, sparky_svg)
    if mood not in MOODS:
        mood = MOOD_NORMAL
    return builder(mood, size)


def avatar_data_uri(who: str, mood: str = MOOD_NORMAL, size: int = 220) -> str:
    """转 base64 data URI，便于放进 <img src>。"""
    svg = avatar_svg(who, mood, size)
    encoded = base64.b64encode(svg.encode("utf-8")).decode("ascii")
    return f"data:image/svg+xml;base64,{encoded}"


def medal_svg(size: int = 260) -> str:
    """通关勋章：金蛋 + 放大镜 + 三颗科学星。"""
    return _svg_wrap(
        '<defs><linearGradient id="gold" x1="0" y1="0" x2="0" y2="1">'
        '<stop offset="0%" stop-color="#FFE9A8"/><stop offset="55%" stop-color="#FFC94D"/>'
        '<stop offset="100%" stop-color="#E9A425"/></linearGradient>'
        '<linearGradient id="ribbon" x1="0" y1="0" x2="1" y2="1">'
        '<stop offset="0%" stop-color="#7CC7F5"/><stop offset="100%" stop-color="#7EC8A0"/></linearGradient></defs>'
        '<path d="M92 150 L64 232 L104 214 L120 244 L140 200 L176 232 L150 148 Z" fill="url(#ribbon)" '
        'stroke="#5BAEDD" stroke-width="3" stroke-linejoin="round"/>'
        '<circle cx="120" cy="104" r="72" fill="url(#gold)" stroke="#D9951C" stroke-width="5" filter="url(#soft)"/>'
        '<circle cx="120" cy="104" r="59" fill="none" stroke="#FFF3C4" stroke-width="3" stroke-dasharray="7 6"/>'
        '<ellipse cx="120" cy="102" rx="30" ry="38" fill="#FFF6D8" stroke="#E9A425" stroke-width="3"/>'
        '<path d="M104 92 q16 -14 32 0" stroke="#E9A425" stroke-width="3" fill="none" stroke-linecap="round"/>'
        '<circle cx="112" cy="98" r="3.4" fill="#4A3B32"/><circle cx="128" cy="98" r="3.4" fill="#4A3B32"/>'
        '<path d="M112 112 q8 8 16 0" stroke="#4A3B32" stroke-width="3" fill="none" stroke-linecap="round"/>'
        '<path d="M150 128 l26 26" stroke="#8A6E4F" stroke-width="8" stroke-linecap="round"/>'
        '<circle cx="146" cy="124" r="17" fill="none" stroke="#8A6E4F" stroke-width="6"/>'
        f"{_sparkles('#FFF3C4')}"
        '<text x="120" y="196" font-size="15" text-anchor="middle" fill="#7A5B18" '
        'font-family="system-ui, sans-serif" font-weight="800">梧桐街金牌小神探</text>',
        size,
        "0 0 240 250",
    )


def egg_svg(size: int = 120, glow: bool = True) -> str:
    """会发光的仿生金蛋（案发现场 / 通关展示用）。"""
    pulse = (
        '<animate attributeName="opacity" values="0.25;0.75;0.25" dur="2.2s" repeatCount="indefinite"/>'
        if glow
        else ""
    )
    return _svg_wrap(
        f'<ellipse cx="120" cy="120" rx="66" ry="76" fill="#FFE9A8" opacity="0.55">{pulse}</ellipse>'
        '<ellipse cx="120" cy="122" rx="52" ry="62" fill="#FFC94D" stroke="#E9A425" stroke-width="4" filter="url(#soft)"/>'
        '<path d="M92 104 q28 -26 56 0" stroke="#FFF3C4" stroke-width="6" fill="none" stroke-linecap="round"/>'
        '<path d="M86 138 q34 22 68 0" stroke="#E9A425" stroke-width="4" fill="none" stroke-linecap="round"/>'
        '<rect x="104" y="118" width="32" height="20" rx="6" fill="#7EC8A0" stroke="#5FAF85" stroke-width="2"/>'
        '<path d="M110 128 h6 l3 -6 l4 12 l3 -6 h6" stroke="#fff" stroke-width="2.2" fill="none" stroke-linejoin="round"/>',
        size,
    )


def scene_svg(size: int = 320) -> str:
    """科学教室案发现场小插画（空展台、水槽、仪器架）。"""
    return _svg_wrap(
        '<rect x="14" y="26" width="212" height="150" rx="16" fill="#EAF6FF" stroke="#BFDCEF" stroke-width="3"/>'
        '<rect x="34" y="44" width="52" height="44" rx="8" fill="#FFF9E6" stroke="#D9C9A3" stroke-width="2.4"/>'
        '<path d="M60 44 v44 M34 66 h52" stroke="#D9C9A3" stroke-width="2"/>'
        '<rect x="120" y="60" width="86" height="60" rx="10" fill="#DFF3EA" stroke="#9CCFB6" stroke-width="3"/>'
        '<path d="M128 96 q18 -14 34 0 q16 14 34 0" stroke="#7EC8A0" stroke-width="3" fill="none"/>'
        '<rect x="26" y="120" width="70" height="56" rx="8" fill="#F3E3C8" stroke="#D9BE93" stroke-width="3"/>'
        '<rect x="34" y="112" width="54" height="12" rx="6" fill="#E7D0AA"/>'
        '<circle cx="61" cy="118" r="4" fill="#FFF3C4" stroke="#E9A425" stroke-width="2"/>'
        '<path d="M40 176 q10 8 20 0 M96 178 q6 6 12 0" stroke="#C9B79A" stroke-width="3" fill="none" stroke-linecap="round"/>'
        '<rect x="150" y="126" width="76" height="50" rx="8" fill="#EFE3F5" stroke="#CBB3DC" stroke-width="3"/>'
        '<path d="M162 126 v-22 M176 126 v-30 M190 126 v-18" stroke="#B79BCB" stroke-width="4" stroke-linecap="round"/>'
        '<circle cx="162" cy="100" r="5" fill="#FF8FA3"/><circle cx="176" cy="92" r="5" fill="#7CC7F5"/>'
        '<circle cx="190" cy="104" r="5" fill="#FFD166"/>'
        f"{_sparkles('#FFE9A8')}",
        size,
        "0 0 240 200",
    )


__all__ = [
    "PALETTE",
    "MOODS",
    "sparky_svg",
    "pan_svg",
    "zhou_svg",
    "zhang_svg",
    "avatar_svg",
    "avatar_data_uri",
    "medal_svg",
    "egg_svg",
    "scene_svg",
    "AVATAR_BUILDERS",
]
