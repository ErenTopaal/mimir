"""
Fuji testnet deployment indexer.
Watches for new contract deployments on Avalanche Fuji C-Chain and auto-triggers audits.
"""
try:
    from uvloop import run  # type: ignore
except ImportError:
    from asyncio import run

import asyncio
import io
import json
import os
import zipfile
from pathlib import Path

import httpx
from loguru import logger


FUJI_RPC = os.getenv('INDEXER_FUJI_RPC', 'https://api.avax-test.network/ext/bc/C/rpc')
SNOWTRACE_API = os.getenv('INDEXER_SNOWTRACE_API', 'https://api-testnet.snowtrace.io/api')
BACKEND_URL = os.getenv('INDEXER_BACKEND_URL', 'http://backend:1337')
POLL_INTERVAL = int(os.getenv('INDEXER_POLL_INTERVAL', '15'))
STATE_FILE = os.getenv('INDEXER_STATE_FILE', '/tmp/indexer_state.json')


def _load_state() -> dict:
    try:
        return json.loads(Path(STATE_FILE).read_text())
    except Exception:
        return {'last_block': 0}


def _save_state(state: dict) -> None:
    with open(STATE_FILE, 'w') as f:
        f.write(json.dumps(state))


async def _get_latest_block(client: httpx.AsyncClient) -> int:
    r = await client.post(FUJI_RPC, json={'jsonrpc': '2.0', 'method': 'eth_blockNumber', 'params': [], 'id': 1})
    return int(r.json()['result'], 16)


async def _get_block_txs(client: httpx.AsyncClient, block_num: int) -> list[dict]:
    r = await client.post(FUJI_RPC, json={
        'jsonrpc': '2.0', 'method': 'eth_getBlockByNumber',
        'params': [hex(block_num), True], 'id': 1,
    })
    block = r.json().get('result') or {}
    return block.get('transactions', [])


async def _get_contract_address(client: httpx.AsyncClient, tx_hash: str) -> str | None:
    r = await client.post(FUJI_RPC, json={
        'jsonrpc': '2.0', 'method': 'eth_getTransactionReceipt',
        'params': [tx_hash], 'id': 1,
    })
    receipt = r.json().get('result') or {}
    return receipt.get('contractAddress')


async def _fetch_source(client: httpx.AsyncClient, address: str) -> dict[str, str] | None:
    r = await client.get(SNOWTRACE_API, params={
        'module': 'contract', 'action': 'getsourcecode', 'address': address,
    })
    data = r.json()
    if data.get('status') != '1' or not data.get('result'):
        return None
    result = data['result'][0]
    source = result.get('SourceCode', '')
    name = result.get('ContractName', 'Contract') or 'Contract'
    if not source:
        return None
    if source.startswith('{{'):
        try:
            parsed = json.loads(source[1:-1])
            return {k: v.get('content', '') for k, v in parsed.get('sources', {}).items()}
        except Exception:
            pass
    return {f'{name}.sol': source}


async def _trigger_audit(client: httpx.AsyncClient, address: str, source_files: dict[str, str]) -> None:
    # Create zip
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        for fname, content in source_files.items():
            zf.writestr(fname, content)

    # POST to backend permalink endpoint to trigger audit
    try:
        r = await client.get(f'{BACKEND_URL}/v1/permalink/fuji/{address}')
        if r.status_code == 200:
            logger.info(f'Triggered/found audit for {address}: {r.json()}')
    except Exception as e:
        logger.warning(f'Failed to trigger audit for {address}: {e}')


async def main() -> None:
    logger.info('Starting Fuji testnet indexer...')
    state = _load_state()

    async with httpx.AsyncClient(timeout=30.0) as client:
        while True:
            try:
                latest = await _get_latest_block(client)
                start = state['last_block'] or (latest - 10)

                for block_num in range(start + 1, min(latest + 1, start + 50)):
                    txs = await _get_block_txs(client, block_num)
                    deploy_txs = [tx for tx in txs if tx.get('to') is None]

                    for tx in deploy_txs:
                        contract_addr = await _get_contract_address(client, tx['hash'])
                        if not contract_addr:
                            continue
                        logger.info(f'New contract deployed: {contract_addr} at block {block_num}')

                        # Wait a bit for source to be verified
                        await asyncio.sleep(2)
                        source = await _fetch_source(client, contract_addr)
                        if source:
                            logger.info(f'Source found for {contract_addr}, triggering audit')
                            await _trigger_audit(client, contract_addr, source)
                        else:
                            logger.info(f'No verified source for {contract_addr}, skipping')

                    state['last_block'] = block_num
                    _save_state(state)

            except Exception as e:
                logger.warning(f'Indexer error: {e}')

            await asyncio.sleep(POLL_INTERVAL)


if __name__ == '__main__':
    run(main())
