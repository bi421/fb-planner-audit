import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from core.precheck import scan_text

print(scan_text("үнэгүй мөнгө"))
