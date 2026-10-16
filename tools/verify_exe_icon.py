"""Verify every embedded EXE icon size and capture Windows' shell icon."""
from pathlib import Path
import argparse
import json
import struct
import ctypes
from ctypes import wintypes

import pefile
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]


def shell_icon(exe):
    class FileInfo(ctypes.Structure):
        _fields_ = [('hIcon', wintypes.HICON), ('iIcon', ctypes.c_int), ('attributes', wintypes.DWORD),
                    ('displayName', wintypes.WCHAR * 260), ('typeName', wintypes.WCHAR * 80)]

    class IconInfo(ctypes.Structure):
        _fields_ = [('isIcon', wintypes.BOOL), ('x', wintypes.DWORD), ('y', wintypes.DWORD),
                    ('mask', wintypes.HBITMAP), ('color', wintypes.HBITMAP)]

    class Bitmap(ctypes.Structure):
        _fields_ = [('type', wintypes.LONG), ('width', wintypes.LONG), ('height', wintypes.LONG),
                    ('rowBytes', wintypes.LONG), ('planes', wintypes.WORD), ('bits', wintypes.WORD), ('data', wintypes.LPVOID)]

    class BitmapHeader(ctypes.Structure):
        _fields_ = [('size', wintypes.DWORD), ('width', wintypes.LONG), ('height', wintypes.LONG),
                    ('planes', wintypes.WORD), ('bits', wintypes.WORD), ('compression', wintypes.DWORD),
                    ('imageSize', wintypes.DWORD), ('x', wintypes.LONG), ('y', wintypes.LONG),
                    ('colors', wintypes.DWORD), ('important', wintypes.DWORD)]

    shell, user, gdi = ctypes.windll.shell32, ctypes.windll.user32, ctypes.windll.gdi32
    shell.SHGetFileInfoW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, ctypes.POINTER(FileInfo), wintypes.UINT, wintypes.UINT]
    shell.SHGetFileInfoW.restype = ctypes.c_size_t
    user.GetIconInfo.argtypes = [wintypes.HICON, ctypes.POINTER(IconInfo)]
    user.DestroyIcon.argtypes = [wintypes.HICON]
    gdi.CreateCompatibleDC.argtypes = [wintypes.HDC]
    gdi.CreateCompatibleDC.restype = wintypes.HDC
    gdi.GetObjectW.argtypes = [wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID]
    gdi.GetDIBits.argtypes = [wintypes.HDC, wintypes.HBITMAP, wintypes.UINT, wintypes.UINT,
                            wintypes.LPVOID, ctypes.POINTER(BitmapHeader), wintypes.UINT]
    gdi.DeleteObject.argtypes = [wintypes.HANDLE]
    gdi.DeleteDC.argtypes = [wintypes.HDC]
    info, details, bitmap = FileInfo(), IconInfo(), Bitmap()
    assert shell.SHGetFileInfoW(str(exe), 0, ctypes.byref(info), ctypes.sizeof(info), 0x100)
    assert user.GetIconInfo(info.hIcon, ctypes.byref(details))
    dc = gdi.CreateCompatibleDC(None)
    try:
        assert gdi.GetObjectW(details.color, ctypes.sizeof(bitmap), ctypes.byref(bitmap))
        width, height = bitmap.width, bitmap.height
        header = BitmapHeader(size=ctypes.sizeof(BitmapHeader), width=width, height=-height, planes=1, bits=32)
        buffer = ctypes.create_string_buffer(width * height * 4)
        assert gdi.GetDIBits(dc, details.color, 0, height, buffer, ctypes.byref(header), 0) == height
        return Image.frombytes('RGBA', (width, height), buffer.raw, 'raw', 'BGRA')
    finally:
        gdi.DeleteDC(dc)
        gdi.DeleteObject(details.color)
        gdi.DeleteObject(details.mask)
        user.DestroyIcon(info.hIcon)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--exe', type=Path, default=ROOT / 'dist/Mogobe/Mogobe.exe')
    exe = parser.parse_args().exe.resolve()
    original = (ROOT / 'assets/ui/app.ico').read_bytes()
    count = struct.unpack_from('<H', original, 4)[0]
    expected = []
    for index in range(count):
        size, offset = struct.unpack_from('<II', original, 6 + index * 16 + 8)
        expected.append(original[offset:offset + size])
    pe = pefile.PE(str(exe))
    actual, groups = [], []
    for kind in pe.DIRECTORY_ENTRY_RESOURCE.entries:
        for entry in kind.directory.entries:
            for language in entry.directory.entries:
                data = pe.get_data(language.data.struct.OffsetToData, language.data.struct.Size)
                if kind.id == 3:
                    actual.append(data)
                elif kind.id == 14:
                    groups.append(data)
    assert len(groups) == 1
    assert len(actual) == count == 7
    assert set(expected) == set(actual)
    widths = [groups[0][6 + index * 14] or 256 for index in range(count)]
    assert sorted(widths) == [16, 24, 32, 48, 64, 128, 256]
    output = ROOT / 'verification/icons' 
    output.mkdir(parents=True, exist_ok=True)
    icon = shell_icon(exe)
    icon.save(output / 'exe-shell-icon.png')
    expected = Image.open(ROOT / 'assets/ui/app.ico').ico.getimage(icon.size).convert('RGBA')
    opaque = [(a, b) for a, b in zip(icon.getdata(), expected.getdata()) if b[3] == 255]
    assert len(opaque) > 100
    matched = sum(max(abs(a[c] - b[c]) for c in range(3)) <= 2 for a, b in opaque)
    assert matched / len(opaque) > .98, 'Windows shell icon does not match the original favicon'
    report = {'exe': str(exe.relative_to(ROOT)), 'all_embedded_sizes_verified': True,
              'sizes': widths, 'windows_shell_icon_extracted': True, 'original_pixels_match': True}
    (output / 'icon-result.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
