"""エラーの種類(spec/vectors.schema.md)。"""


class AuthFoundationError(Exception):
    """判定の部品が投げるエラー。``code`` にエラーの種類(``unknown_site`` など)を持つ。"""

    def __init__(self, code, detail=None):
        super().__init__(code if detail is None else "%s: %s" % (code, detail))
        self.code = code
        self.detail = detail
