"""Bounded acquisition campaigns and a single joint research catalog.

GitHub CLI is used only for publishing/retrieving this repository's releases.
Public source restrictions are recorded, never worked around.
"""
import argparse
import datetime as dt
import json
import os
import shutil
import subprocess
import time
import zipfile
from pathlib import Path, PurePosixPath

import pandas as pd

from .acquire import KLINES, atomic_json, download, download_one, plan, sha256, utcnow, fetch
from .macro import acquire_macro
from .publish import assets
from .research import audit, write_frame
from .trades import audit_trades


def load(path):
    return json.loads(Path(path).read_text())


def gh(*args):
    return subprocess.check_output(['gh', *args], text=True)


def prepare(root, symbol, month):
    config = load(root / 'config/research.json')
    start = dt.date.fromisoformat(month + '-01')
    end = (start.replace(day=28) + dt.timedelta(days=4)).replace(day=1)
    config.update(start=max(config['start'], start.isoformat()),
                  end_exclusive=min(config['end_exclusive'], end.isoformat()), symbols=[symbol])
    requested = plan(config)
    keys = {r['key'] for r in requested}
    records = [r for r in load(root / 'manifests/acquisition.json') if r['key'] in keys]
    atomic_json(root / 'config/research.json', config)
    atomic_json(root / 'manifests/requested.json', requested)
    atomic_json(root / 'manifests/acquisition.json', records)
    return config


def repair_whole_missing_days(config, root):
    """Retrieve official daily counterparts for whole days missing inside monthly candles.

    Partial-day gaps remain explicit to avoid silently selecting overlapping sources.
    """
    records = load(root / 'manifests/acquisition.json')
    repairs = []
    for source in list(records):
        if source['status'] != 'verified' or source['period'] != 'monthly' or source['category'] not in KLINES:
            continue
        path = root / f"data/normalized/{source['symbol']}/{source['category']}/1m.csv.gz"
        grid = pd.read_csv(path, index_col=0, parse_dates=True)
        for day, section in grid.groupby(grid.index.floor('D')):
            if day.strftime('%Y-%m') != source['date'] or len(section) != 1440 or section.close.notna().any():
                continue
            daily_config = dict(config, start=day.strftime('%Y-%m-%d'),
                                end_exclusive=(day + pd.Timedelta(days=1)).strftime('%Y-%m-%d'),
                                symbols=[source['symbol']], categories=[source['category']])
            item = plan(daily_config)[0]
            result = download_one(item, root)
            result['repair_for'] = source['key']
            repairs.append(result)
    indexed = {r['key']: r for r in records}
    indexed.update({r['key']: r for r in repairs})
    atomic_json(root / 'manifests/acquisition.json', sorted(indexed.values(), key=lambda r: r['key']))
    return repairs


def acquire_campaign(root, symbol, month):
    started = time.monotonic()
    config = prepare(root, symbol, month)
    download(config, root, workers=6)
    audit(config, root)
    repairs = repair_whole_missing_days(config, root)
    if any(r['status'] == 'verified' for r in repairs):
        audit(config, root)
    audit_trades(config, root)
    packaged = assets(root)
    tag = f"campaign-{symbol}-{month}-{os.environ['GITHUB_RUN_ID']}-{os.environ['GITHUB_RUN_ATTEMPT']}"
    metadata = root / 'campaign-metadata'
    metadata.mkdir(exist_ok=True)
    for source, target in [('manifests/acquisition.json', 'ACQUISITION.json'),
                           ('reports/quality.json', 'QUALITY.json'),
                           ('reports/trades_full.json', 'TRADES_FULL.json'),
                           ('config/research.json', 'CONFIG.json')]:
        shutil.copyfile(root / source, root / 'release-assets' / target)
        shutil.copyfile(root / source, metadata / target)
    atomic_json(metadata / 'ASSETS.json', packaged)
    atomic_json(metadata / 'CAMPAIGN.json', {'symbol': symbol, 'month': month, 'tag': tag,
                'status': 'prepared', 'effective_work_seconds': time.monotonic() - started,
                'measured_scope': 'automated acquisition, validation and packaging; excludes queue time',
                'generated_at_utc': utcnow()})
    gh('release', 'create', tag, '--title', f'{symbol} {month} verified source campaign',
       '--notes-file', str(root / 'reports/QUALITY.md'), '--target', os.environ['GITHUB_SHA'])
    gh('release', 'upload', tag, *[str(p) for p in sorted((root / 'release-assets').iterdir())])
    actual = json.loads(gh('release', 'view', tag, '--json', 'assets,url'))
    by_name = {a['name']: a for a in actual['assets']}
    for asset in packaged:
        remote = by_name[asset['asset']]
        if remote['size'] != asset['bytes']:
            raise ValueError('Published asset size mismatch')
        if remote.get('digest') and remote['digest'] != 'sha256:' + asset['sha256']:
            raise ValueError('Published asset digest mismatch')
        asset['url'] = remote['url']
    atomic_json(metadata / 'ASSETS.json', packaged)
    campaign = load(metadata / 'CAMPAIGN.json')
    campaign.update(status='published', release_url=actual['url'],
                    effective_work_seconds=time.monotonic() - started)
    atomic_json(metadata / 'CAMPAIGN.json', campaign)
    print(json.dumps(campaign), flush=True)


def merge_metadata(root, metadata):
    config = load(root / 'config/research.json')
    expected = {(s, m) for s in config['symbols'] for m in ['2026-05','2026-06','2026-07','2026-08','2026-09','2026-10']}
    campaigns, all_assets, records, trades = [], [], {}, {}
    scopes = set()
    for folder in sorted(metadata.iterdir()):
        if not folder.is_dir():
            continue
        campaign = load(folder / 'CAMPAIGN.json')
        scope = (campaign['symbol'], campaign['month'])
        if scope in scopes or scope not in expected or campaign['status'] != 'published':
            raise ValueError(f'Duplicate, unexpected or unpublished campaign: {scope}')
        scopes.add(scope)
        campaigns.append(campaign)
        for asset in load(folder / 'ASSETS.json'):
            all_assets.append(dict(asset, tag=campaign['tag'], symbol=campaign['symbol'], month=campaign['month']))
        for record in load(folder / 'ACQUISITION.json'):
            if record['key'] in records:
                raise ValueError('Source belongs to multiple campaign scopes: ' + record['key'])
            records[record['key']] = record
        for record in load(folder / 'TRADES_FULL.json')['partitions']:
            if record['key'] in trades:
                raise ValueError('Duplicate trade partition')
            trades[record['key']] = record
    if scopes != expected:
        raise ValueError(f'Campaigns not published: {sorted(expected - scopes)}')
    atomic_json(root / 'manifests/acquisition.json', sorted(records.values(), key=lambda r: r['key']))
    atomic_json(root / 'reports/trades_full.json', {'generated_at_utc': utcnow(),
                'partitions': sorted(trades.values(), key=lambda r: (r['symbol'], r['date'])),
                'note': 'All rows audited within each daily partition; joint boundary checks added separately.'})
    return config, campaigns, all_assets


def retrieve_nontrade_sources(root, all_assets):
    scratch = root / 'campaign-download'
    scratch.mkdir(exist_ok=True)
    for asset in all_assets:
        members = [m for m in asset['members'] if m.startswith('data/raw/') and '/trades/' not in m]
        if not members:
            continue
        gh('release', 'download', asset['tag'], '--pattern', asset['asset'], '--dir', str(scratch))
        archive_path = scratch / asset['asset']
        if sha256(archive_path) != asset['sha256']:
            raise ValueError('Campaign asset SHA256 mismatch')
        with zipfile.ZipFile(archive_path) as archive:
            for member in members:
                path = PurePosixPath(member)
                if path.is_absolute() or '..' in path.parts:
                    raise ValueError('Unsafe archive member')
                archive.extract(member, root)
        archive_path.unlink()


def restore_macro_checkpoint(root):
    """Preserve already acquired context if a new public fetch becomes unavailable."""
    scratch = root / 'campaign-download'
    gh('release','download','dataset-2026-10-09','--pattern','Binance_BTC_ETH_Research.zip','--dir',str(scratch))
    archive_path = scratch / 'Binance_BTC_ETH_Research.zip'
    if sha256(archive_path) != '09dc56a968bdcb6b5e685d392abd9ffc38ba1dd671500b194f2471728ba620cd':
        raise ValueError('Initial checkpoint SHA256 mismatch')
    prefix = 'binance-btc-eth-research/'
    with zipfile.ZipFile(archive_path) as archive:
        for name in archive.namelist():
            relative = name.removeprefix(prefix)
            if relative.startswith(('data/raw/macro/','data/normalized/macro/','data/normalized/execution_costs/')):
                dest = root / relative
                dest.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(name) as source, dest.open('wb') as target:
                    shutil.copyfileobj(source, target)
    archive_path.unlink()


def funding_api_context(config, root):
    """Bounded official history pagination; stop on any access/region restriction."""
    from urllib.parse import urlencode
    results = []
    start = int(pd.Timestamp(config['start'], tz='UTC').timestamp()*1000)
    end = int(pd.Timestamp(config['end_exclusive'], tz='UTC').timestamp()*1000)-1
    for symbol in config['symbols']:
        target = root / f'data/raw/api/fundingRate/{symbol}.json'
        record = dict(symbol=symbol,retrieved_at_utc=utcnow(),official_checksum_available=False,pages=[])
        try:
            values, cursor, finished = [], start, False
            for page_number in range(1,6):
                url = 'https://fapi.binance.com/fapi/v1/fundingRate?' + urlencode(
                    dict(symbol=symbol,startTime=cursor,endTime=end,limit=1000))
                page_path=target.with_name(f'{symbol}-page-{page_number}.json')
                fetch(url,page_path,attempts=1)
                page=load(page_path)
                if not isinstance(page,list) or any(r.get('symbol') != symbol for r in page):
                    raise ValueError('Unexpected funding history schema')
                record['pages'].append(dict(url=url,sha256=sha256(page_path),rows=len(page),
                                            relative_path=str(page_path.relative_to(root))))
                values.extend(page)
                if len(page)<1000:
                    finished=True
                    break
                next_cursor=int(page[-1]['fundingTime'])+1
                if next_cursor<=cursor:
                    raise ValueError('Funding pagination did not advance')
                cursor=next_cursor
            atomic_json(target,values)
            frame = pd.DataFrame(values)
            if len(frame):
                frame['event_time_utc'] = pd.to_datetime(frame.fundingTime,unit='ms',utc=True)
                frame['last_funding_rate'] = pd.to_numeric(frame.fundingRate,errors='raise')
                if frame.fundingTime.duplicated().any() or not frame.fundingTime.is_monotonic_increasing:
                    raise ValueError('Funding timestamps not unique and ordered')
                if ((frame.fundingTime<start)|(frame.fundingTime>end)).any():
                    raise ValueError('Funding history outside requested window')
                write_frame(frame,root/f'data/normalized/{symbol}/funding_api.csv.gz',index=False)
            record.update(status='acquired',rows=len(values),sha256=sha256(target),
                          relative_path=str(target.relative_to(root)),
                          pagination_complete=finished)
        except Exception as exc:
            record.update(status='unavailable',error=str(exc))
        results.append(record)
    atomic_json(root/'manifests/funding_api.json',results)
    return results


def joint_panel(config, root):
    panel = None
    for symbol in config['symbols']:
        frame = pd.read_csv(root / f'data/features/{symbol}/1m.csv.gz', index_col=0, parse_dates=True)
        columns = ['close','volume','quote_volume','return_1m','atr_14','rsi_14','ema_20','ema_50',
                   'ema_200','volatility_30m','volatility_60m','trend_20_50_bps','data_valid']
        frame = frame[columns].add_prefix(symbol + '_')
        for category in ['markPriceKlines','indexPriceKlines','premiumIndexKlines']:
            aux = pd.read_csv(root / f'data/normalized/{symbol}/{category}/1m.csv.gz', index_col=0, parse_dates=True)
            frame[symbol + '_' + category] = aux.close
        metrics_path = root / f'data/normalized/{symbol}/metrics.csv.gz'
        if metrics_path.exists():
            metrics = pd.read_csv(metrics_path)
            metrics.index = pd.to_datetime(metrics.event_time_utc, utc=True)
            duplicate = metrics.index.duplicated(keep=False)
            ambiguous = metrics.index[duplicate].unique()
            metrics = metrics[~duplicate]
            # Only exact timestamps: no interpolation or assumption of historical availability.
            frame[symbol + '_open_interest_exact'] = metrics.sum_open_interest.reindex(frame.index)
            frame[symbol + '_open_interest_ambiguous'] = frame.index.isin(ambiguous)
        panel = frame if panel is None else panel.join(frame, how='outer')
    panel['bar_available_at_utc'] = panel.index + pd.Timedelta(minutes=1)
    panel['both_ohlcv_valid'] = panel[[s+'_data_valid' for s in config['symbols']]].all(axis=1)
    panel['macro_point_in_time_certified'] = False
    panel['l2_price_level_history_available'] = False
    panel['account_execution_costs_observed'] = False
    panel.index.name = 'open_time_utc'
    write_frame(panel, root / 'data/joint/BTC_ETH_1m.csv.gz')
    return len(panel)


def consolidate(root, metadata):
    started = time.monotonic()
    config, campaigns, all_assets = merge_metadata(root, metadata)
    retrieve_nontrade_sources(root, all_assets)
    restore_macro_checkpoint(root)
    nontrade_config = dict(config, categories=[c for c in config['categories'] if c != 'trades'])
    audit(nontrade_config, root)
    quality = load(root / 'reports/quality.json')
    records = load(root / 'manifests/acquisition.json')
    requested = plan(config)
    indexed = {r['key']: r for r in records}
    quality['window'] = config
    quality['missing_files'] = [r for r in requested if indexed.get(r['key'], {}).get('status') != 'verified']
    partitions = load(root / 'reports/trades_full.json')['partitions']
    boundary_errors = []
    for symbol in config['symbols']:
        subset = sorted((r for r in partitions if r['symbol'] == symbol), key=lambda r: r['date'])
        for left, right in zip(subset, subset[1:]):
            consecutive_day = pd.Timestamp(right['date']) - pd.Timestamp(left['date']) == pd.Timedelta(days=1)
            if consecutive_day and left.get('last_id') is not None and right.get('first_id') is not None:
                if right['first_id'] <= left['last_id'] or right['first_time_ms'] < left['last_time_ms']:
                    boundary_errors.append({'left': left['key'], 'right': right['key']})
        quality['coverage'].append({'symbol': symbol, 'category': 'trades',
            'verified_files': sum(r['symbol']==symbol and r['category']=='trades' and r['status']=='verified' for r in records),
            'expected_files': sum(r['symbol']==symbol and r['category']=='trades' for r in requested),
            'observed_rows': sum(r['rows'] for r in subset),
            'fully_audited_files': sum(r['status']=='audited_all_rows' for r in subset)})
    quality.update(trade_semantics='full_rows_per_acquired_daily_partition', trade_boundary_errors=boundary_errors)
    atomic_json(root / 'reports/quality.json', quality)
    previous_macro = load(root/'manifests/macro.json')
    previous_events=load(root/'data/normalized/macro/scheduled_events.json')
    acquire_macro(config, root)
    macro = load(root/'manifests/macro.json')
    previous_index = {r.get('series',r.get('event_type')):r for r in previous_macro}
    for i, record in enumerate(macro):
        old = previous_index.get(record.get('series',record.get('event_type')))
        if record['status'] != 'acquired' and old and old['status']=='acquired':
            target = root/old['relative_path']
            if target.exists() and sha256(target)==old['sha256']:
                macro[i] = dict(old,resumed_from_initial_release=True,new_fetch_error=record.get('error'))
    atomic_json(root/'manifests/macro.json',macro)
    events={ (r['event_type'],r['scheduled_release_at_utc']):r for r in previous_events }
    events.update({(r['event_type'],r['scheduled_release_at_utc']):r
                  for r in load(root/'data/normalized/macro/scheduled_events.json')})
    atomic_json(root/'data/normalized/macro/scheduled_events.json',sorted(events.values(),key=lambda r:r['scheduled_release_at_utc']))
    funding_api = funding_api_context(config,root)
    rows = joint_panel(config, root)
    derived = [{'relative_path':str(p.relative_to(root)),'bytes':p.stat().st_size,'sha256':sha256(p)}
               for p in sorted((root/'data').rglob('*')) if p.is_file() and 'raw' not in p.relative_to(root).parts]
    atomic_json(root/'manifests/derived_files.json',derived)
    bad = [r for r in partitions if r['status'] != 'audited_all_rows' or any(r.get(k, 0) for k in
           ['invalid_rows','non_increasing_id_transitions','regressing_time_transitions','outside_partition_rows','quote_product_mismatch_rows'])]
    core_complete = not bad and not boundary_errors and all(
        r['verified_files'] == r['expected_files'] and not r.get('missing_rows', 0)
        for r in quality['coverage'] if r['category'] in ['klines', 'trades']) and not quality['errors']
    summary = {'generated_at_utc': utcnow(), 'requested_source_files': len(requested),
               'verified_source_files': sum(indexed.get(r['key'],{}).get('status')=='verified' for r in requested),
               'remaining_source_files': len(quality['missing_files']), 'joint_panel_rows': rows,
               'ohlcv_and_trades_complete_and_audited': core_complete,
               'all_requested_categories_complete': False,
               'l2_status': 'full_price_level_history_not_acquired',
               'macro_status': 'latest_vintage_not_point_in_time_certified',
               'execution_cost_status': 'scenario_assumptions_not_account_observations',
               'trade_invalid_partitions': len(bad), 'trade_boundary_errors': len(boundary_errors),
               'funding_api_sources':funding_api,'macro_sources':macro,
               'campaigns': campaigns, 'campaign_data_assets': all_assets,
               'effective_work_seconds': time.monotonic() - started,
               'active_time_measurement': 'consolidation only; campaign durations reported independently and may overlap'}
    atomic_json(root / 'reports/JOINT_DELIVERY.json', summary)
    atomic_json(root / 'manifests/requested.json', requested)
    report = ['# BTC y ETH: catálogo conjunto', '', f"Fuentes verificadas: {summary['verified_source_files']}/{len(requested)}.",
              f"Fuentes pendientes: {summary['remaining_source_files']}. Panel conjunto: {rows} minutos UTC.",
              f"OHLCV y trades completos y auditados: {core_complete}.", '',
              'El panel BTC_ETH_1m.csv.gz alinea ambos activos en UTC. Los indicadores se recalculan sobre los cinco meses completos, sin reinicio artificial al cambiar de mes.',
              'El OI se une sólo en timestamps exactos. No se presupone su disponibilidad histórica intrabar.', '',
              'L2 histórico por niveles no adquirido. bookDepth conserva su identidad de profundidad agregada.',
              'Macro: última revisión disponible, sin certificación point-in-time. Costos: escenarios, no costos reales de una cuenta.', '',
              'JOINT_DELIVERY.json contiene todos los Releases de particiones, miembros, tamaños y hashes. Los ZIP conjuntos contienen velas, auxiliares, indicadores y macro; los trades completos están en los Releases mensuales enlazados.', '',
              'Consultar QUALITY.json, TRADES_FULL.json, ACQUISITION.json y MISSING.json. Los faltantes no se rellenan.']
    (root / 'reports/JOINT_DELIVERY.md').write_text('\n\n'.join(report)+'\n')
    packaged = assets(root)
    dest = root / 'release-assets'
    for source, target in [('reports/quality.json','QUALITY.json'),('reports/trades_full.json','TRADES_FULL.json'),
                           ('manifests/acquisition.json','ACQUISITION.json'),('reports/JOINT_DELIVERY.json','JOINT_DELIVERY.json'),
                           ('reports/JOINT_DELIVERY.md','JOINT_DELIVERY.md'),('manifests/macro.json','MACRO.json'),
                           ('manifests/funding_api.json','FUNDING_API.json')]:
        shutil.copyfile(root / source, dest / target)
    atomic_json(dest / 'MISSING.json', quality['missing_files'])
    tag = f"joint-BTC-ETH-{os.environ['GITHUB_RUN_ID']}-{os.environ['GITHUB_RUN_ATTEMPT']}"
    gh('release', 'create', tag, '--title', 'BTC + ETH: conjunto de cinco meses y auditoría integral',
       '--notes-file', str(root / 'reports/JOINT_DELIVERY.md'), '--target', os.environ['GITHUB_SHA'])
    gh('release', 'upload', tag, *[str(p) for p in sorted(dest.iterdir())])
    remote = json.loads(gh('release','view',tag,'--json','assets,url'))
    indexed_assets = {a['name']: a for a in remote['assets']}
    for item in packaged:
        observed = indexed_assets[item['asset']]
        if observed['size'] != item['bytes'] or (observed.get('digest') and observed['digest'] != 'sha256:'+item['sha256']):
            raise ValueError('Joint release asset verification failed')
    summary.update(release_url=remote['url'],remote_repository_created=True,remote_data_uploaded=True,
                   planned_source_files=len(requested),publication_verified_at_utc=utcnow())
    atomic_json(root/'reports/JOINT_DELIVERY.json',summary)
    atomic_json(root/'reports/delivery.json',summary)
    quality['github']={'repository_created':True,'data_uploaded':True,'release_url':remote['url']}
    atomic_json(root/'reports/quality.json',quality)
    text=(root/'reports/JOINT_DELIVERY.md').read_text()
    text += '\nRelease conjunta publicada: '+remote['url']+'\n'
    (root/'reports/DELIVERY.md').write_text(text)
    (root/'reports/JOINT_DELIVERY.md').write_text(text)
    for source,target in [('reports/JOINT_DELIVERY.json','JOINT_DELIVERY.json'),('reports/quality.json','QUALITY.json'),
                          ('reports/JOINT_DELIVERY.md','JOINT_DELIVERY.md')]:
        shutil.copyfile(root/source,dest/target)
        gh('release','upload',tag,str(dest/target),'--clobber')
    print(json.dumps({'release_url':remote['url'], 'summary':summary}, ensure_ascii=False), flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=['acquire','consolidate'])
    parser.add_argument('--symbol', choices=['BTCUSDT','ETHUSDT'])
    parser.add_argument('--month')
    parser.add_argument('--metadata', default='campaign-input')
    args = parser.parse_args()
    root = Path('.').resolve()
    if args.command == 'acquire':
        acquire_campaign(root, args.symbol, args.month)
    else:
        consolidate(root, root / args.metadata)


if __name__ == '__main__':
    main()
