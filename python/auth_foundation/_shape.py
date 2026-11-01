"""値の形の読み方。JS 版と同じにする(spec/vectors.schema.md §1「値の形」)。"""


def get(obj, key):
    """オブジェクトでなければ None。"""
    return obj.get(key) if isinstance(obj, dict) else None


def items(value):
    """配列でなければ空の配列(文字列を部分一致で読まないため)。"""
    return value if isinstance(value, list) else []


def is_int(v):
    """整数の値の数(1 も 1.0 も整数。JS では見分けられないため)。真偽値は整数でない。"""
    if isinstance(v, bool):
        return False
    if isinstance(v, int):
        return True
    return isinstance(v, float) and v.is_integer()
