"""Contract management endpoints."""
import time
from fastapi import APIRouter, HTTPException

from ..database import db
from ..models.schemas import CreateContractRequest, ContractResponse, Contract

router = APIRouter(prefix="/contracts", tags=["contracts"])


@router.get("")
async def get_contracts() -> dict:
    """Get all contracts."""
    rows = await db.fetch_all(
        """
        SELECT 
            id, address, name, tags,
            CASE WHEN abi_json IS NOT NULL THEN true ELSE false END as has_abi,
            is_watched, created_at
        FROM contracts
        ORDER BY created_at DESC
        """
    )
    
    contracts = [
        Contract(
            id=row["id"],
            address=row["address"],
            name=row["name"],
            tags=row["tags"] or [],
            has_abi=row["has_abi"],
            is_watched=row["is_watched"],
            created_at=row["created_at"],
        )
        for row in rows
    ]
    
    return {"contracts": contracts}


@router.post("")
async def create_contract(request: CreateContractRequest) -> ContractResponse:
    """Add a contract to the watchlist."""
    # Validate address format
    address = request.address.lower()
    if not address.startswith("0x") or len(address) != 42:
        raise HTTPException(status_code=400, detail="Invalid address format")
    
    # Check if contract already exists
    existing = await db.fetch_one(
        "SELECT id FROM contracts WHERE LOWER(address) = $1",
        address,
    )
    
    if existing:
        raise HTTPException(status_code=409, detail="Contract already exists")
    
    # Insert contract
    now = int(time.time())
    row = await db.fetch_one(
        """
        INSERT INTO contracts (address, name, tags, abi_json, is_watched, created_at, updated_at)
        VALUES ($1, $2, $3, $4, true, $5, $5)
        RETURNING id, address, name, tags, 
            CASE WHEN abi_json IS NOT NULL THEN true ELSE false END as has_abi,
            is_watched, created_at
        """,
        address,
        request.name,
        request.tags,
        request.abi_json,
        now,
    )
    
    contract = Contract(
        id=row["id"],
        address=row["address"],
        name=row["name"],
        tags=row["tags"] or [],
        has_abi=row["has_abi"],
        is_watched=row["is_watched"],
        created_at=row["created_at"],
    )
    
    return ContractResponse(contract=contract)
