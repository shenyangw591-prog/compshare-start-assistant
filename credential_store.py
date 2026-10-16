"""Windows 当前用户 DPAPI 凭证存储；仅密文落盘，无第三方依赖。"""
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import tempfile


class CredentialError(Exception):
    pass


class DataBlob(ctypes.Structure):
    _fields_ = [("size", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_ubyte))]


def _crypt(data, decrypt=False):
    if os.name != "nt":
        raise CredentialError("记住密钥仅支持 Windows，当前仍可临时输入使用。")
    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    blob_ptr = ctypes.POINTER(DataBlob)
    crypt32.CryptProtectData.argtypes = [blob_ptr, wintypes.LPCWSTR, blob_ptr,
                                        ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, blob_ptr]
    crypt32.CryptProtectData.restype = wintypes.BOOL
    crypt32.CryptUnprotectData.argtypes = [blob_ptr, ctypes.POINTER(wintypes.LPWSTR), blob_ptr,
                                          ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, blob_ptr]
    crypt32.CryptUnprotectData.restype = wintypes.BOOL
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p
    buffer = ctypes.create_string_buffer(data)
    incoming = DataBlob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    outgoing = DataBlob()
    function = crypt32.CryptUnprotectData if decrypt else crypt32.CryptProtectData
    description = None if decrypt else "CompShare Start credentials"
    if not function(ctypes.byref(incoming), description, None, None, None,
                    1, ctypes.byref(outgoing)):  # CRYPTPROTECT_UI_FORBIDDEN；不使用 LOCAL_MACHINE。
        raise CredentialError("Windows 无法解密已保存的密钥，请重新输入。" if decrypt
                              else "Windows 加密失败，密钥未保存。")
    try:
        return ctypes.string_at(outgoing.data, outgoing.size)
    finally:
        kernel32.LocalFree(ctypes.cast(outgoing.data, ctypes.c_void_p))


class CredentialStore:
    available = os.name == "nt"

    def __init__(self, path=None):
        base = Path(os.getenv("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
        self.path = Path(path) if path is not None else base / "CompShareStart" / "credentials.bin"

    @staticmethod
    def _validate(value):
        if (not isinstance(value, dict) or value.get("version") != 1
                or any(not isinstance(value.get(key), str) or len(value[key]) > 4096
                       for key in ("public_key", "private_key", "project_id"))
                or not value["public_key"].strip() or not value["private_key"].strip()):
            raise CredentialError("保存的密钥格式无效，请重新输入。")
        return {key: value[key] for key in ("public_key", "private_key", "project_id")}

    def load(self):
        try:
            with self.path.open("rb") as stream:
                encrypted = stream.read(65537)
        except FileNotFoundError:
            return None
        except OSError:
            raise CredentialError("无法读取已保存的密钥，请重新输入。") from None
        if len(encrypted) > 65536 or not encrypted.startswith(b"CSK1"):
            raise CredentialError("保存的密钥文件已损坏，请清除后重新输入。")
        try:
            value = json.loads(_crypt(encrypted[4:], decrypt=True).decode("utf-8"))
            return self._validate(value)
        except (ValueError, UnicodeError):
            raise CredentialError("保存的密钥文件已损坏，请清除后重新输入。") from None

    def save(self, public_key, private_key, project_id=""):
        value = dict(version=1, public_key=public_key, private_key=private_key, project_id=project_id)
        self._validate(value)
        encrypted = b"CSK1" + _crypt(json.dumps(value, ensure_ascii=False).encode("utf-8"))
        temporary = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=self.path.parent, prefix="credentials-", suffix=".tmp", delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(encrypted)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
        except OSError:
            raise CredentialError("无法写入密钥文件，本次仍可使用，请检查文件夹权限。") from None
        finally:
            if temporary is not None:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    pass

    def delete(self):
        try:
            self.path.unlink(missing_ok=True)
        except OSError:
            raise CredentialError("无法清除已保存的密钥，请检查文件权限。") from None
