import json
import tempfile
import unittest
from pathlib import Path

from quantdata.acquire import atomic_json, plan
from quantdata.research import audit
from quantdata.trades import audit_trades
from quantdata.campaign import prepare, merge_metadata


class CampaignScopeTests(unittest.TestCase):
    def config(self):
        return dict(market='futures/um',symbols=['BTCUSDT','ETHUSDT'],start='2026-05-09',
                    end_exclusive='2026-10-09',interval='1m',categories=['markPriceKlines','trades'])

    def test_month_scope_does_not_audit_other_months_missing_local_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = self.config()
            atomic_json(root/'config/research.json',config)
            records = plan(config)
            for r in records:
                r.update(status='verified',relative_path='missing-source.zip',source_sha256='0'*64)
            atomic_json(root/'manifests/acquisition.json',records)
            scoped = prepare(root,'ETHUSDT','2026-06')
            self.assertEqual(scoped['start'],'2026-06-01')
            self.assertEqual(scoped['end_exclusive'],'2026-07-01')
            self.assertTrue(all(r['symbol']=='ETHUSDT' and r['date'].startswith('2026-06')
                                for r in json.loads((root/'manifests/acquisition.json').read_text())))

    def test_foreign_verified_sources_do_not_contaminate_audit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = dict(self.config(),symbols=['ETHUSDT'],categories=['markPriceKlines'],
                          start='2026-06-01',end_exclusive='2026-06-02')
            foreign = plan(dict(config,start='2026-05-09',end_exclusive='2026-05-10'))[0]
            foreign.update(status='verified',relative_path='nonexistent.zip',source_sha256='0'*64)
            atomic_json(root/'manifests/acquisition.json',[foreign])
            audit(config,root)
            self.assertEqual(json.loads((root/'reports/quality.json').read_text())['errors'],[])
            foreign['category']='trades'
            atomic_json(root/'manifests/acquisition.json',[foreign])
            self.assertEqual(audit_trades(dict(config,categories=['trades']),root),[])

    def test_joint_catalog_rejects_missing_campaigns(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            atomic_json(root/'config/research.json',self.config())
            (root/'campaign-input').mkdir()
            with self.assertRaisesRegex(ValueError,'Campaigns not published'):
                merge_metadata(root,root/'campaign-input')


if __name__=='__main__':
    unittest.main()
