#!/usr/bin/env python3
"""
Build script for LCSC Grabber standalone installer.
Creates platform-specific executables using PyInstaller.

Usage:
    python scripts/build.py          # Build for current platform
    python scripts/build.py --clean  # Clean build artifacts first
"""

import os
import sys
import shutil
import subprocess
import platform
from pathlib import Path


def get_project_root():
    """Get the project root directory."""
    return Path(__file__).parent.parent


def clean_build_artifacts(project_root: Path):
    """Remove build artifacts."""
    dirs_to_remove = ['build', 'dist', '__pycache__']
    files_to_remove = ['*.pyc', '*.pyo']

    for dir_name in dirs_to_remove:
        dir_path = project_root / dir_name
        if dir_path.exists():
            print(f"Removing {dir_path}")
            shutil.rmtree(dir_path)

    # Clean __pycache__ recursively
    for pycache in project_root.rglob('__pycache__'):
        print(f"Removing {pycache}")
        shutil.rmtree(pycache)


def convert_icon_to_ico(project_root: Path):
    """Convert PNG icon to ICO for Windows."""
    png_path = project_root / 'resources' / 'icon.png'
    ico_path = project_root / 'resources' / 'icon.ico'

    if ico_path.exists():
        return ico_path

    if not png_path.exists():
        print("Warning: icon.png not found")
        return None

    try:
        from PIL import Image
        img = Image.open(png_path)
        img.save(ico_path, format='ICO', sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)])
        print(f"Created {ico_path}")
        return ico_path
    except ImportError:
        print("Warning: Pillow not installed, cannot convert icon to ICO")
        print("Install with: pip install Pillow")
        return None


def convert_icon_to_icns(project_root: Path):
    """Convert PNG icon to ICNS for macOS."""
    png_path = project_root / 'resources' / 'icon.png'
    icns_path = project_root / 'resources' / 'icon.icns'

    if icns_path.exists():
        return icns_path

    if not png_path.exists():
        print("Warning: icon.png not found")
        return None

    if platform.system() == 'Darwin':
        # Use macOS iconutil
        iconset_path = project_root / 'resources' / 'icon.iconset'
        iconset_path.mkdir(exist_ok=True)

        try:
            from PIL import Image
            img = Image.open(png_path)

            sizes = [16, 32, 64, 128, 256, 512]
            for size in sizes:
                resized = img.resize((size, size), Image.LANCZOS)
                resized.save(iconset_path / f'icon_{size}x{size}.png')
                resized_2x = img.resize((size * 2, size * 2), Image.LANCZOS)
                resized_2x.save(iconset_path / f'icon_{size}x{size}@2x.png')

            subprocess.run(['iconutil', '-c', 'icns', str(iconset_path)], check=True)
            shutil.rmtree(iconset_path)
            print(f"Created {icns_path}")
            return icns_path
        except Exception as e:
            print(f"Warning: Could not create ICNS: {e}")
            if iconset_path.exists():
                shutil.rmtree(iconset_path)
            return None

    return None


def build_executable(project_root: Path):
    """Build the executable using PyInstaller."""
    # Ensure we're in the project root
    os.chdir(project_root)

    # Convert icons for the current platform
    system = platform.system()
    if system == 'Windows':
        convert_icon_to_ico(project_root)
    elif system == 'Darwin':
        convert_icon_to_icns(project_root)

    # Build using PyInstaller
    spec_file = project_root / 'lcsc_grabber.spec'

    cmd = [
        sys.executable, '-m', 'PyInstaller',
        '--clean',
        '--noconfirm',
        str(spec_file)
    ]

    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=project_root)

    if result.returncode != 0:
        print("Build failed!")
        sys.exit(1)

    # Report output location
    dist_dir = project_root / 'dist'
    if system == 'Windows':
        exe_path = dist_dir / 'LCSC-Grabber.exe'
    elif system == 'Darwin':
        exe_path = dist_dir / 'LCSC Grabber.app'
    else:
        exe_path = dist_dir / 'lcsc-grabber'

    if exe_path.exists():
        print(f"\nBuild successful!")
        print(f"Output: {exe_path}")

        # Get file size
        if exe_path.is_file():
            size_mb = exe_path.stat().st_size / (1024 * 1024)
            print(f"Size: {size_mb:.1f} MB")
    else:
        print(f"\nWarning: Expected output not found at {exe_path}")
        print(f"Contents of dist/: {list(dist_dir.iterdir()) if dist_dir.exists() else 'N/A'}")


def create_release_archive(project_root: Path):
    """Create a release archive with the built executable."""
    dist_dir = project_root / 'dist'
    system = platform.system().lower()
    arch = platform.machine().lower()

    # Normalize architecture names
    if arch in ('x86_64', 'amd64'):
        arch = 'x64'
    elif arch in ('aarch64', 'arm64'):
        arch = 'arm64'

    version = '1.1.0'
    archive_name = f'lcsc-grabber-{version}-{system}-{arch}'

    if system == 'windows':
        # Create ZIP for Windows
        archive_path = dist_dir / f'{archive_name}.zip'
        exe_path = dist_dir / 'LCSC-Grabber.exe'
        if exe_path.exists():
            import zipfile
            with zipfile.ZipFile(archive_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                zf.write(exe_path, 'LCSC-Grabber.exe')
            print(f"Created: {archive_path}")
    elif system == 'darwin':
        # Create DMG or ZIP for macOS
        archive_path = dist_dir / f'{archive_name}.zip'
        app_path = dist_dir / 'LCSC Grabber.app'
        if app_path.exists():
            shutil.make_archive(str(dist_dir / archive_name), 'zip', dist_dir, 'LCSC Grabber.app')
            print(f"Created: {archive_path}")
    else:
        # Create tar.gz for Linux
        archive_path = dist_dir / f'{archive_name}.tar.gz'
        exe_path = dist_dir / 'lcsc-grabber'
        if exe_path.exists():
            import tarfile
            with tarfile.open(archive_path, 'w:gz') as tf:
                tf.add(exe_path, 'lcsc-grabber')
            print(f"Created: {archive_path}")


def main():
    project_root = get_project_root()

    # Parse arguments
    clean = '--clean' in sys.argv
    archive = '--archive' in sys.argv

    if clean:
        print("Cleaning build artifacts...")
        clean_build_artifacts(project_root)

    print(f"Building LCSC Grabber for {platform.system()} ({platform.machine()})...")
    build_executable(project_root)

    if archive:
        print("\nCreating release archive...")
        create_release_archive(project_root)


if __name__ == '__main__':
    main()
