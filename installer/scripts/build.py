#!/usr/bin/env python3
"""
RClone GUI 统一构建入口
用法:
    cd installer/scripts
    python build.py pyinstaller [--debug] [--onedir]
    python build.py nuitka [--debug] [--standalone]
    python build.py all          # 同时构建两种
"""

import sys
import argparse


def main():
    parser = argparse.ArgumentParser(description="RClone GUI 统一构建脚本")
    sub = parser.add_subparsers(dest="builder", help="选择打包工具")

    # PyInstaller
    pi = sub.add_parser("pyinstaller", aliases=["pi"], help="使用 PyInstaller 打包")
    pi.add_argument("--debug", action="store_true")
    pi.add_argument("--onedir", action="store_true")

    # Nuitka
    nk = sub.add_parser("nuitka", aliases=["nk"], help="使用 Nuitka 打包")
    nk.add_argument("--debug", action="store_true")
    nk.add_argument("--standalone", action="store_true")

    # All
    sub.add_parser("all", help="同时使用两种工具打包")

    args = parser.parse_args()

    if not args.builder:
        parser.print_help()
        sys.exit(1)

    if args.builder in ("pyinstaller", "pi"):
        from build_pyinstaller import build
        build(debug=args.debug, onedir=args.onedir)

    elif args.builder in ("nuitka", "nk"):
        from build_nuitka import build
        build(debug=args.debug, standalone=args.standalone)

    elif args.builder == "all":
        print("=" * 60)
        print("  阶段 1/2: PyInstaller")
        print("=" * 60)
        from build_pyinstaller import build as pi_build
        pi_build()

        print("\n" + "=" * 60)
        print("  阶段 2/2: Nuitka")
        print("=" * 60)
        from build_nuitka import build as nk_build
        nk_build()

        print("\n✅ 全部构建完成！")


if __name__ == "__main__":
    main()
