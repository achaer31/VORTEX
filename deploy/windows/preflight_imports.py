"""Offline import check. File invocation avoids Windows PowerShell 5.1 -c quoting."""
import sys


def main():
    try:
        import MetaTrader5
        import pandas
        import numpy
        expected = ((MetaTrader5, "5.0.6180"), (pandas, "2.2.3"), (numpy, "2.3.5"))
        if any(module.__version__ != version for module, version in expected):
            raise ValueError()
    except Exception:
        print("Pinned dependency import check failed; terminal untouched.", file=sys.stderr)
        return 2
    print("Pinned imports OK; no terminal connection attempted.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
