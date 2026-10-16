"""Windows x64 发布包构建。白名单打包，不收集本地配置或日志。"""
import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parent
VERSION = "0.4.6"
SOURCE_FILES = ["app.py", "credential_store.py", "test_credential_store.py", "editorial_layout.py", "ui_layout.py", "ui_widgets.py", "assets/app.manifest", "start_instance.py", "test_start_instance.py", "test_gui.py",
                "build_release.py", "requirements-build.txt", "config.example.json",
                "start.cmd", "启动图形界面.cmd", "体验演示模式.cmd", "使用说明.md",
                "README.md", "LICENSE", "CHANGELOG.md", ".gitignore",
                ".github/workflows/build.yml", "assets/icon.ico", "assets/icon.png",
                "assets/icon.svg", "assets/brand.png", "assets/brand-header-100.png",
                "assets/brand-header-125.png", "assets/brand-header-150.png", "assets/prepare_brand.py",
                "docs/preview.png", "docs/render_preview.py", "docs/PUBLISHING.md"]


def make_zip(path, files):
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        for source, name in files:
            archive.write(source, name)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-build", action="store_true", help="使用现有 dist/CompShareStart.exe")
    args = parser.parse_args()
    os.chdir(ROOT)
    release = ROOT / "release"
    release.mkdir(exist_ok=True)
    if not args.skip_build:
        subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--onefile", "--windowed",
            "--noupx", "--name", "CompShareStart", "--manifest", str(ROOT / "assets/app.manifest"), "--icon", str(ROOT / "assets/icon.ico"),
            "--add-data", f"{ROOT / 'assets'}:assets", "--distpath", "dist", "--workpath", "build",
            "--specpath", "build", "app.py"], check=True)
    exe = ROOT / "dist/CompShareStart.exe"
    if not exe.exists():
        raise SystemExit("未找到 EXE，请先在 Windows 上完成构建")
    source_zip = release / f"CompShareStart-v{VERSION}-source.zip"
    windows_zip = release / f"CompShareStart-v{VERSION}-windows-x64.zip"
    make_zip(source_zip, [(ROOT / name, f"CompShareStart/{name}") for name in SOURCE_FILES])
    demo_launcher = release / "体验演示模式.cmd"
    demo_launcher.write_bytes('@echo off\r\ncd /d "%~dp0"\r\nstart "" "CompShareStart.exe" --demo\r\n'.encode("utf-8"))
    quickstart = release / "先看这里.txt"
    quickstart.write_text("CompShare 开机助手 v" + VERSION + "\n\n"
        "1. 解压整个文件夹，双击 CompShareStart.exe（无需 Python）。\n"
        "2. 粘贴账户中心的 API 公钥 / 私钥，点击连接。\n"
        "3. 点选已有实例，点击开始自动开机。\n\n"
        "第一次使用可以打开“帮助”→“体验离线演示”，无需密钥。\n"
        "请保持电脑联网、不休眠。开机后正常计费，用完自行关机。\n"
        "关闭助手只停止本地等待，不撤销已提交的云端开机请求。\n"
        "这是非官方社区工具，不能保证一定抢到。\n"
        "勾选记住密钥后，Windows 会在本机加密保存，下次自动填入。\n"
        "取消勾选或点击清除即可删除；密钥不写入日志，不要发给任何人。\n\n"
        "本版本已完成离线测试，并依据用户反馈适配缺卡错误 226604；尚未验证真实开机成功。\n", encoding="utf-8-sig")
    licenses_dir = release / "THIRD_PARTY_LICENSES"
    licenses_dir.mkdir(exist_ok=True)
    # 收集实际构建环境中的依赖许可证，不依赖作者绝对路径。
    for name in ("LICENSE_PYTHON.txt", "LICENSE.txt"):
        python_license = Path(sys.base_prefix) / name
        if python_license.exists():
            (licenses_dir / "Python.txt").write_bytes(python_license.read_bytes())
            break
    for name in ("tcl8.6", "tk8.6"):
        for base in (Path(sys.base_prefix) / "tcl", Path(sys.base_prefix) / "Library/lib"):
            license_file = base / name / "license.terms"
            if license_file.exists():
                (licenses_dir / f"{name}.txt").write_bytes(license_file.read_bytes())
                break
    # Conda 的 Tcl / OpenSSL 许可证可能放在包缓存，而非运行时目录。
    metadata_dir = Path(sys.base_prefix) / "conda-meta"
    if metadata_dir.exists():
        for pattern in ("tk-*.json", "openssl-*.json"):
            for metadata_path in metadata_dir.glob(pattern):
                meta = json.loads(metadata_path.read_text(encoding="utf-8"))
                package_dir = Path(sys.base_prefix) / "pkgs" / f"{meta['name']}-{meta['version']}-{meta['build']}"
                cached_licenses = package_dir / "info/licenses"
                if cached_licenses.exists():
                    for license_file in cached_licenses.rglob("*"):
                        if license_file.is_file():
                            relative = "-".join(license_file.relative_to(cached_licenses).parts)
                            (licenses_dir / f"{meta['name']}-{relative}").write_bytes(license_file.read_bytes())
    distribution = importlib.metadata.distribution("pyinstaller")
    for file in distribution.files or []:
        if "/licenses/" in str(file).replace("\\", "/"):
            source = Path(distribution.locate_file(file))
            if source.is_file():
                (licenses_dir / ("PyInstaller-" + source.name)).write_bytes(source.read_bytes())
    bundle = [(exe, "CompShareStart/CompShareStart.exe"),
              (demo_launcher, "CompShareStart/体验演示模式.cmd"),
              (quickstart, "CompShareStart/先看这里.txt"),
              (ROOT / "README.md", "CompShareStart/README.md"),
              (ROOT / "LICENSE", "CompShareStart/LICENSE"),
              (ROOT / "CHANGELOG.md", "CompShareStart/CHANGELOG.md"),
              (ROOT / "docs/preview.png", "CompShareStart/docs/preview.png"),
              (ROOT / "docs/PUBLISHING.md", "CompShareStart/docs/PUBLISHING.md"),
              (ROOT / "使用说明.md", "CompShareStart/使用说明.md")]
    bundle.extend((p, f"CompShareStart/THIRD_PARTY_LICENSES/{p.name}") for p in licenses_dir.iterdir() if p.is_file())
    make_zip(windows_zip, bundle)
    checksum_paths = [source_zip, windows_zip]
    (release / "SHA256SUMS.txt").write_text("".join(
        f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}\n" for path in checksum_paths), encoding="ascii")
    manifest = {"version": VERSION, "packages": [{"name": p.name, "size": p.stat().st_size,
                "sha256": hashlib.sha256(p.read_bytes()).hexdigest()} for p in checksum_paths],
                "validation": "offline only; no live account tested"}
    (release / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    for path in checksum_paths:
        print(f"{path.name}: {path.stat().st_size / 1024 / 1024:.2f} MB")


if __name__ == "__main__":
    main()
