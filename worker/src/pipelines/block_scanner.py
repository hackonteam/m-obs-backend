"""Block scanner and transaction ingestion pipeline."""
import asyncio
import logging
import time
from typing import Optional

from ..config import config
from ..database import db
from ..providers.manager import provider_manager
from ..providers.rpc_client import RPCError
from ..decoders.error_decoder import extract_error_signature, decode_error
from ..state.worker_state import get_last_scanned_block, set_last_scanned_block

logger = logging.getLogger(__name__)


class BlockScanner:
    """Scans new blocks and ingests transactions."""

    def __init__(self) -> None:
        self.last_block_hash: Optional[str] = None
        self.catching_up = False

    async def run(self) -> None:
        """Run scanner loop indefinitely."""
        logger.info("Starting block scanner pipeline")
        
        while True:
            try:
                await self.scan_cycle()
                
                # Adaptive polling
                interval = 0.5 if self.catching_up else config.poll_interval_scanner
                await asyncio.sleep(interval)
            
            except Exception as e:
                logger.error(f"Scan cycle error: {e}")
                await asyncio.sleep(5)

    async def scan_cycle(self) -> None:
        """Execute one scan cycle."""
        # Get current chain state
        provider_id, provider = await provider_manager.get_primary()
        
        try:
            current_block = await provider.eth_block_number()
        except RPCError as e:
            logger.error(f"Failed to get block number: {e}")
            await provider_manager.mark_failure(provider_id)
            return
        
        # Get last scanned block from state
        state = await get_last_scanned_block()
        last_scanned = state["block_number"]
        
        if current_block <= last_scanned:
            self.catching_up = False
            return
        
        # Determine batch size
        blocks_behind = current_block - last_scanned
        self.catching_up = blocks_behind > 10
        
        batch_size = min(config.block_batch_size, blocks_behind) if self.catching_up else 1
        
        logger.info(
            f"Scanning blocks {last_scanned + 1} to {last_scanned + batch_size} "
            f"(behind: {blocks_behind})"
        )
        
        # Scan blocks
        for block_num in range(last_scanned + 1, last_scanned + batch_size + 1):
            await self.scan_block(block_num, provider_id, provider)

    async def scan_block(self, block_num: int, provider_id: int, provider) -> None:
        """Scan single block and ingest transactions."""
        try:
            # Fetch block with transactions
            block = await provider.eth_get_block_by_number(block_num, full_txs=True)
            
            if not block:
                logger.warning(f"Block {block_num} not found")
                return
            
            # Verify parent hash for reorg detection
            if self.last_block_hash and block.get("parentHash") != self.last_block_hash:
                logger.warning(f"Reorg detected at block {block_num}!")
                await self.handle_reorg(block_num)
                return
            
            # Process transactions
            transactions = block.get("transactions", [])
            block_timestamp = int(block.get("timestamp", "0x0"), 16)
            
            if transactions:
                await self.process_transactions(transactions, block_num, block_timestamp)
            
            # Update state
            self.last_block_hash = block.get("hash")
            await set_last_scanned_block(block_num, self.last_block_hash)
            
            logger.info(f"Scanned block {block_num} with {len(transactions)} transactions")
        
        except RPCError as e:
            logger.error(f"Failed to scan block {block_num}: {e}")
            await provider_manager.mark_failure(provider_id)
            raise

    async def process_transactions(
        self, 
        transactions: list[dict], 
        block_number: int,
        block_timestamp: int,
    ) -> None:
        """Process and store transactions from block."""
        # Fetch receipts for all transactions
        provider_id, provider = await provider_manager.get_primary()
        
        tx_data = []
        
        for tx in transactions:
            try:
                # Get receipt
                receipt = await provider.eth_get_transaction_receipt(tx["hash"])
                
                # Extract transaction data
                tx_hash = tx["hash"]
                from_address = tx["from"]
                to_address = tx.get("to")  # None for contract creation
                value_wei = int(tx.get("value", "0x0"), 16)
                gas_used = int(receipt.get("gasUsed", "0x0"), 16)
                gas_price = int(tx.get("gasPrice", "0x0"), 16)
                status = int(receipt.get("status", "0x0"), 16)
                
                # Extract method ID
                method_id = None
                input_data = tx.get("input", "0x")
                if input_data and len(input_data) >= 10 and input_data != "0x":
                    method_id = input_data[:10]
                
                # Handle failed transactions
                error_raw = None
                error_signature = None
                error_decoded = None
                error_params = None
                
                if status == 0:
                    # Extract revert reason
                    revert_reason = receipt.get("revertReason")
                    if revert_reason:
                        error_raw = revert_reason
                        error_signature = extract_error_signature(revert_reason)
                        decoded_msg, params = decode_error(revert_reason)
                        error_decoded = decoded_msg
                        error_params = params
                
                # Match contract (if to_address exists)
                contract_id = None
                if to_address:
                    contract_row = await db.fetch_one(
                        "SELECT id FROM contracts WHERE LOWER(address) = LOWER($1) AND is_watched = true",
                        to_address,
                    )
                    if contract_row:
                        contract_id = contract_row["id"]
                
                tx_data.append((
                    tx_hash,
                    block_number,
                    block_timestamp,
                    from_address,
                    to_address,
                    contract_id,
                    value_wei,
                    gas_used,
                    gas_price,
                    status,
                    error_raw,
                    error_signature,
                    error_decoded,
                    error_params,
                    method_id,
                    None,  # method_name (TODO: decode from ABI)
                    False,  # has_trace
                    False,  # is_tentative
                    int(time.time()),
                ))
            
            except Exception as e:
                logger.error(f"Failed to process tx {tx.get('hash')}: {e}")
                continue
        
        # Batch insert transactions
        if tx_data:
            await db.execute_many(
                """
                INSERT INTO txs (
                    hash, block_number, block_timestamp, from_address, to_address,
                    contract_id, value_wei, gas_used, gas_price, status,
                    error_raw, error_signature, error_decoded, error_params,
                    method_id, method_name, has_trace, is_tentative, ingested_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19)
                ON CONFLICT (hash) DO NOTHING
                """,
                tx_data,
            )
            
            logger.info(f"Inserted {len(tx_data)} transactions")

    async def handle_reorg(self, block_num: int) -> None:
        """Handle blockchain reorganization."""
        logger.warning(f"Handling reorg at block {block_num}")
        
        # Mark recent transactions as tentative
        await db.execute(
            """
            UPDATE txs 
            SET is_tentative = true 
            WHERE block_number >= $1
            """,
            block_num - 10,  # Mark last 10 blocks as tentative
        )
        
        # Rollback scanner state
        new_last_block = max(0, block_num - 20)
        await set_last_scanned_block(new_last_block, "0x0")
        self.last_block_hash = None
        
        logger.info(f"Rolled back to block {new_last_block}")


scanner = BlockScanner()
