"""時刻の形(spec/vectors.schema.md §5)。datetime を使わず、JS 版と同じ手順で読む。"""
import re

from .errors import AuthFoundationError

_RE = re.compile(r"([0-9]{4})-([0-9]{2})-([0-9]{2})T([0-9]{2}):([0-9]{2}):([0-9]{2})"
                 r"(?:\.([0-9]{1,6}))?(Z|([+-])([0-9]{2}):([0-9]{2}))")
_DAYS = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)


def _leap(y):
    return y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)


def _days_from_civil(y, m, d):
    # 1970-01-01 からの日数(0000〜9999 年)
    y -= 1 if m <= 2 else 0
    era = y // 400
    yoe = y - era * 400
    doy = (153 * (m + (-3 if m > 2 else 9)) + 2) // 5 + d - 1
    doe = yoe * 365 + yoe // 4 - yoe // 100 + doy
    return era * 146097 + doe - 719468


def parse_time(value):
    """時刻を (秒, マイクロ秒) の組にする。形が違えば None。"""
    if not isinstance(value, str):
        return None
    m = _RE.fullmatch(value)
    if not m:
        return None
    y, mo, d, h, mi, s = (int(m.group(i)) for i in range(1, 7))
    frac = m.group(7)
    if not (1 <= mo <= 12) or d < 1 or h > 23 or mi > 59 or s > 59:
        return None
    dim = 29 if (mo == 2 and _leap(y)) else _DAYS[mo - 1]
    if d > dim:
        return None
    off = 0
    if m.group(8) != "Z":
        oh, om = int(m.group(10)), int(m.group(11))
        if oh > 23 or om > 59:
            return None
        off = (oh * 3600 + om * 60) * (1 if m.group(9) == "+" else -1)
    secs = _days_from_civil(y, mo, d) * 86400 + h * 3600 + mi * 60 + s - off
    micros = int((frac or "").ljust(6, "0") or "0")
    return (secs, micros)


def require_time(value):
    t = parse_time(value)
    if t is None:
        raise AuthFoundationError("invalid_time", value)
    return t
