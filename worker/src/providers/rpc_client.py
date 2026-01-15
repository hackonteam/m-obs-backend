"""JSON-RPC client for Ethereum-compatible nodes."""
import asyncio
import httpx
from typing import Any, Optional
import logging

from ..config import config

logger = logging.getLogger(__name__)


class RPCClient:
    """Async JSON-RPC 2.0 client."""

    def __init__(self, url: str, timeout: int = 5) -> None:
        self.url = url
        self.timeout = timeout
        self._request_id = 0

    async def call(
        self,
        method: str,
        params: list[Any] | None = None,
        timeout: Optional[int] = None,
    ) -> Any:
        """Make JSON-RPC call."""
        self._request_id += 1
        
        payload = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params or [],
            "id": self._request_id,
        }
        
        timeout_val = timeout or self.timeout
        
        try:
            async with httpx.AsyncClient(timeout=timeout_val) as client:
                response = await client.post(self.url, json=payload)
                response.raise_for_status()
                
                data = response.json()
                
                if "error" in data:
                    raise RPCError(
                        code=data["error"].get("code"),
                        message=data["error"].get("message"),
                    )
                
                return data.get("result")
        
        except httpx.TimeoutException:
            raise RPCError(code=-32001, message="Request timeout")
        except httpx.HTTPError as e:
            raise RPCError(code=-32002, message=f"HTTP error: {e}")
        except Exception as e:
            raise RPCError(code=-32003, message=f"Unknown error: {e}")

    async def eth_block_number(self) -> int:
        """Get latest block number."""
        result = await self.call("eth_blockNumber")
        return int(result, 16)

    async def eth_get_block_by_number(
        self, block_number: int, full_txs: bool = True
    ) -> dict:
        """Get block by number."""
        block_hex = hex(block_number)
        return await self.call("eth_getBlockByNumber", [block_hex, full_txs])

    async def eth_get_transaction_receipt(self, tx_hash: str) -> dict:
        """Get transaction receipt."""
        return await self.call("eth_getTransactionReceipt", [tx_hash])

    async def debug_trace_transaction(
        self, tx_hash: str, tracer: str = "callTracer"
    ) -> dict:
        """Get execution trace (debug API)."""
        return await self.call(
            "debug_traceTransaction",
            [tx_hash, {"tracer": tracer}],
            timeout=config.rpc_timeout_trace,
        )

    async def eth_call(self, tx: dict, block: str = "latest") -> str:
        """Execute call without creating transaction."""
        return await self.call("eth_call", [tx, block])


class RPCError(Exception):
    """RPC error exception."""

    def __init__(self, code: Optional[int] = None, message: str = "RPC error") -> None:
        self.code = code
        self.message = message
        super().__init__(f"RPC Error {code}: {message}")
