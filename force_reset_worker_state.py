#!/usr/bin/env python3
"""
Force reset worker state - completely delete and recreate.
This ensures no caching issues.
"""
import asyncio
import asyncpg
import json
import time


DATABASE_URL = "postgresql://postgres.yiwvntjytcacakkanben:H4ck0n_2026@aws-1-ap-south-1.pooler.supabase.com:6543/postgres"


async def force_reset():
    """Force reset worker state."""
    
    print(f"\n🔥 FORCE RESET WORKER STATE")
    print(f"=" * 60)
    
    try:
        # Connect
        print("\n🔌 Connecting to database...")
        conn = await asyncpg.connect(
            DATABASE_URL,
            ssl='require',
            statement_cache_size=0,
            command_timeout=30
        )
        print("✅ Connected!")
        
        # Get current block
        print("\n📡 Getting current blockchain state...")
        import httpx
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                "https://mantle-rpc.publicnode.com",
                json={"jsonrpc":"2.0","method":"eth_blockNumber","params":[],"id":1}
            )
            data = resp.json()
            current_block = int(data['result'], 16)
            target_block = current_block - 100
            print(f"   Current block: {current_block:,}")
            print(f"   Target block: {target_block:,}")
        
        # DELETE old state completely
        print(f"\n🗑️  Deleting old state...")
        result = await conn.execute(
            "DELETE FROM worker_state WHERE key = 'last_scanned_block'"
        )
        print(f"   Deleted: {result}")
        
        # Verify deletion
        check = await conn.fetchrow(
            "SELECT * FROM worker_state WHERE key = 'last_scanned_block'"
        )
        if check:
            print(f"   ⚠️  WARNING: State still exists!")
        else:
            print(f"   ✅ State deleted successfully")
        
        # INSERT new state (fresh)
        print(f"\n📝 Creating new state...")
        new_state = {
            "block_number": target_block,
            "block_hash": "0x0",
            "timestamp": int(time.time())
        }
        
        result = await conn.execute(
            """
            INSERT INTO worker_state (key, value, updated_at)
            VALUES ($1, $2, $3)
            """,
            "last_scanned_block",
            json.dumps(new_state),
            int(time.time())
        )
        print(f"   Inserted: {result}")
        
        # Verify
        print(f"\n🔍 Verifying new state...")
        row = await conn.fetchrow(
            "SELECT * FROM worker_state WHERE key = 'last_scanned_block'"
        )
        
        if row:
            print(f"   ✅ State verified!")
            print(f"   Key: {row['key']}")
            print(f"   Value: {row['value']}")
            
            # Parse and check
            value_data = json.loads(row['value'])
            if value_data['block_number'] == target_block:
                print(f"   ✅ Block number correct: {target_block:,}")
            else:
                print(f"   ❌ Block number mismatch!")
                print(f"      Expected: {target_block}")
                print(f"      Got: {value_data['block_number']}")
        else:
            print(f"   ❌ State not found after insert!")
        
        await conn.close()
        
        print(f"\n" + "=" * 60)
        print(f"✅ FORCE RESET COMPLETE!")
        print(f"=" * 60)
        print(f"\n📋 Next Steps:")
        print(f"   1. RESTART worker service NOW")
        print(f"   2. Check logs for: 'Scanning blocks {target_block + 1}'")
        print(f"   3. If still fails, worker may be caching state in code")
        print(f"\n")
        
        return True
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    import sys
    success = asyncio.run(force_reset())
    sys.exit(0 if success else 1)
