#!/usr/bin/env python3
"""
Script to update worker state directly in database.
This forces the worker to skip to recent blocks for real-time monitoring.
"""
import asyncio
import asyncpg
import json
import time
import sys
from datetime import datetime


# Database configuration
DATABASE_URL = "postgresql://postgres.yiwvntjytcacakkanben:H4ck0n_2026@aws-1-ap-south-1.pooler.supabase.com:6543/postgres"


async def get_current_state(conn):
    """Get current worker state from database."""
    row = await conn.fetchrow(
        "SELECT key, value, updated_at FROM worker_state WHERE key = $1",
        "last_scanned_block"
    )
    
    if row:
        print(f"\n📊 Current State:")
        print(f"   Key: {row['key']}")
        print(f"   Value: {row['value']}")
        print(f"   Updated at: {datetime.fromtimestamp(row['updated_at'])}")
        
        # Try to parse value
        try:
            value_data = json.loads(row['value']) if isinstance(row['value'], str) else row['value']
            print(f"   Block number: {value_data.get('block_number', 'N/A')}")
        except:
            print(f"   ⚠️  Could not parse value as JSON")
    else:
        print("\n❌ No state found in database")
    
    return row


async def update_worker_state(target_block: int):
    """Update worker state to target block."""
    
    print(f"\n🔧 Updating Worker State")
    print(f"=" * 60)
    print(f"Target block: {target_block:,}")
    print(f"Database: {DATABASE_URL.split('@')[1].split('/')[0]}")
    print(f"=" * 60)
    
    try:
        # Connect to database
        print("\n🔌 Connecting to database...")
        conn = await asyncpg.connect(
            DATABASE_URL,
            ssl='require',
            statement_cache_size=0,
            command_timeout=30
        )
        print("✅ Connected successfully!")
        
        # Get current state
        await get_current_state(conn)
        
        # Prepare new state
        new_state = {
            "block_number": target_block,
            "block_hash": "0x0",
            "timestamp": int(time.time())
        }
        new_state_json = json.dumps(new_state)
        current_timestamp = int(time.time())
        
        print(f"\n📝 New State:")
        print(f"   {json.dumps(new_state, indent=2)}")
        
        # Update state
        print(f"\n⚙️  Updating database...")
        result = await conn.execute(
            """
            INSERT INTO worker_state (key, value, updated_at)
            VALUES ($1, $2, $3)
            ON CONFLICT (key) 
            DO UPDATE SET 
                value = EXCLUDED.value,
                updated_at = EXCLUDED.updated_at
            """,
            "last_scanned_block",
            new_state_json,
            current_timestamp
        )
        
        print(f"✅ Update successful: {result}")
        
        # Verify update
        print(f"\n🔍 Verifying update...")
        updated_row = await get_current_state(conn)
        
        if updated_row:
            try:
                value_data = json.loads(updated_row['value']) if isinstance(updated_row['value'], str) else updated_row['value']
                if value_data.get('block_number') == target_block:
                    print(f"\n✅ Verification SUCCESS!")
                    print(f"   Worker will start from block {target_block:,}")
                else:
                    print(f"\n⚠️  Verification FAILED!")
                    print(f"   Expected: {target_block}")
                    print(f"   Got: {value_data.get('block_number')}")
            except Exception as e:
                print(f"\n⚠️  Could not verify: {e}")
        
        # Close connection
        await conn.close()
        print(f"\n🔌 Database connection closed")
        
        print(f"\n" + "=" * 60)
        print(f"✅ WORKER STATE UPDATED SUCCESSFULLY!")
        print(f"=" * 60)
        print(f"\n📋 Next Steps:")
        print(f"   1. Restart your worker service")
        print(f"   2. Check worker logs for: 'Scanning blocks {target_block + 1}'")
        print(f"   3. Worker should catch up in 5-10 minutes")
        print(f"\n")
        
        return True
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        print(f"\nFull error details:")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """Main function."""
    # Get target block from command line or use default
    if len(sys.argv) > 1:
        target_block = int(sys.argv[1])
    else:
        # Default: recent block (90,163,532 based on current chain state)
        target_block = 90163532
    
    success = await update_worker_state(target_block)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())
