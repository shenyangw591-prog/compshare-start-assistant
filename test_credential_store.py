"""只用虚构密钥测试 DPAPI，文件位于本项目临时目录，不访问用户凭证。"""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from credential_store import CredentialStore, CredentialError


@unittest.skipUnless(CredentialStore.available, "DPAPI 仅 Windows 支持")
class CredentialTests(unittest.TestCase):
    def setUp(self):
        base = Path(__file__).resolve().parent / ".build-cache"
        base.mkdir(exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(prefix="credential-test-", dir=base)
        self.directory = Path(self.temporary.name)
        assert self.directory.resolve().is_relative_to(base.resolve())
        self.addCleanup(self.temporary.cleanup)
        self.store = CredentialStore(self.directory / "profile" / "credentials.bin")

    def test_encrypted_roundtrip_after_reopen(self):
        self.assertIsNone(self.store.load())
        self.store.save("synthetic-public-01", "synthetic-private-02", "test-project")
        encrypted = self.store.path.read_bytes()
        for value in (b"synthetic-public-01", b"synthetic-private-02", b"test-project"):
            self.assertNotIn(value, encrypted)
        reopened = CredentialStore(self.store.path)
        self.assertEqual(reopened.load(), dict(public_key="synthetic-public-01",
                                              private_key="synthetic-private-02", project_id="test-project"))

    def test_encrypt_failure_keeps_previous_file(self):
        self.store.save("old-public", "old-private")
        before = self.store.path.read_bytes()
        with patch("credential_store._crypt", side_effect=CredentialError("加密失败")):
            with self.assertRaises(CredentialError):
                self.store.save("new-public", "new-private")
        self.assertEqual(before, self.store.path.read_bytes())
        self.assertEqual(self.store.load()["private_key"], "old-private")

    def test_replace_failure_keeps_previous_file_and_cleans_temporary(self):
        self.store.save("old-public", "old-private")
        with patch("credential_store.os.replace", side_effect=PermissionError()):
            with self.assertRaises(CredentialError):
                self.store.save("new-public", "new-private")
        self.assertEqual(self.store.load()["private_key"], "old-private")
        self.assertEqual(list(self.store.path.parent.glob("*.tmp")), [])

    def test_corrupt_or_invalid_file_is_rejected(self):
        self.store.save("fake-public", "fake-private")
        encrypted = self.store.path.read_bytes()
        for broken in (b"not a credential", encrypted[:len(encrypted)//2], b"CSK1" + b"x"*65537):
            with self.subTest(size=len(broken)):
                self.store.path.write_bytes(broken)
                with self.assertRaises(CredentialError):
                    self.store.load()

    def test_forget_removes_saved_credentials(self):
        self.store.save("fake-public", "fake-private")
        self.store.delete()
        self.assertFalse(self.store.path.exists())
        self.assertIsNone(self.store.load())
        self.store.delete()


if __name__ == "__main__":
    unittest.main()
