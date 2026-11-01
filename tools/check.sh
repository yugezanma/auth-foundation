#!/bin/sh
# Python 版と JS 版のテストをまとめて流す。どちらかが落ちたら 1 で終わる。
set -e
cd "$(dirname "$0")/.."
echo "== Python"
python3 -m unittest discover -s python/tests
echo "== JS"
node --test js/test/
