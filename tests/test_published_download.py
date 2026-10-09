import tempfile
import unittest
import zipfile
from pathlib import Path

from quantdata.acquire import sha256
from quantdata.fetch_published import extract_verified


class PublishedDownloadTests(unittest.TestCase):
    def fixture(self, root, members):
        path = root/'asset.zip'
        with zipfile.ZipFile(path, 'w') as out:
            for member in members:
                out.writestr(member, b'test')
        return path, dict(asset=path.name, bytes=path.stat().st_size, sha256=sha256(path), members=members)

    def test_monthly_features_cannot_overwrite_joint_features(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            member = 'data/features/BTCUSDT/1m.csv.gz'
            dest = root/'result'
            (dest/member).parent.mkdir(parents=True)
            (dest/member).write_bytes(b'joint full-window features')
            raw = 'data/raw/futures/um/daily/trades/BTCUSDT/part.zip'
            path, asset = self.fixture(root, [member, raw])
            extract_verified(path, asset, dest, trades_only=True)
            self.assertEqual((dest/member).read_bytes(), b'joint full-window features')
            self.assertEqual((dest/raw).read_bytes(), b'test')

    def test_corrupt_asset_and_unsafe_member_fail_before_extracting(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            path, asset = self.fixture(root, ['data/raw/good.zip', '../outside'])
            dest = root/'result'
            with self.assertRaises(ValueError):
                extract_verified(path, asset, dest)
            self.assertFalse((dest/'data/raw/good.zip').exists())
            path.write_bytes(path.read_bytes()+b'corruption')
            with self.assertRaises(ValueError):
                extract_verified(path, asset, dest)


if __name__ == '__main__':
    unittest.main()
