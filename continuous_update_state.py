#!/usr/bin/env python3
"""
Continuously update worker state until worker picks it up.
This works even while worker is running.
"""
import asyncio
import asyncpg
import json
import time


DATABASE_URL = "postgresql://postgres.yiwvntjytcacakkanben:H4ck0n_2026@aws-1-ap-south-1.pooler.supabase.com:6543/postgres"


async def get_target_block():
    """Get target block from RPC."""
    import httpx
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            "https://mantle-rpc.publicnode.com",
            json={"jsonrpc":"2.0","method":"eth_blockNumber","params":[],"id":1}
        )
        data = resp.json()
        current_block = int(data['result'], 16)
        return current_block - 100


async def continuous_update():
    """Continuously update state."""
    
    print(f"\n🔄 CONTINUOUS STATE UPDATER")
    print(f"=" * 60)
    print(f"This will keep updating worker state until worker picks it up.")
    print(f"Press Ctrl+C to stop.\n")
    
    try:
        # Connect
        conn = await asyncpg.connect(
            DATABASE_URL,
            ssl='require',
            statement_cache_size=0,
            command_timeout=30
        )
        print("✅ Connected to database\n")
        
        # Get target
        target_block = await get_target_block()
        print(f"🎯 Target block: {target_block:,}\n")
        
        iteration = 0
        last_worker_block = None
        
        while True:
            iteration += 1
            
            # Read current state
            row = await conn.fetchrow(
                "SELECT value FROM worker_state WHERE key = 'last_scanned_block'"
            )
            
            if row:
                try:
                    value_data = json.loads(row['value'])
                    current_block = value_data.get('block_number', 0)
                    
                    # Check if worker picked up our change
                    if current_block >= target_block:
                        print(f"\n✅ SUCCESS! Worker picked up new state!")
                        print(f"   Current block: {current_block:,}")
                        print(f"   Target block: {target_block:,}")
                        break
                    
                    # Track worker progress
                    if current_block != last_worker_block:
                        print(f"[{iteration:3d}] Worker at block: {current_block:,} (updating to {target_block:,})")
                        last_worker_block = current_block
                    else:
                        print(f"[{iteration:3d}] Updating... (worker at {current_block:,})")
                    
                except Exception as e:
                    print(f"[{iteration:3d}] Parse error: {e}")
            
            # Update state
            new_state = {
                "block_number": target_block,
                "block_hash": "0x0",
                "timestamp": int(time.time())
            }
            
            await conn.execute(
                """
                UPDATE worker_state 
                SET value = $1, updated_at = $2
                WHERE key = 'last_scanned_block'
                """,
                json.dumps(new_state),
                int(time.time())
            )
            
            # Wait a bit
            await asyncio.sleep(2)
        
        await conn.close()
        
        print(f"\n" + "=" * 60)
        print(f"✅ WORKER STATE SUCCESSFULLY UPDATED!")
        print(f"=" * 60)
        print(f"\nWorker will now scan from block {target_block:,}")
        print(f"Check logs for: 'Scanning blocks {target_block + 1}'\n")
        
        return True
        
    except KeyboardInterrupt:
        print(f"\n\n⚠️  Stopped by user")
        return False
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    import sys
    success = asyncio.run(continuous_update())
    sys.exit(0 if success else 1)
