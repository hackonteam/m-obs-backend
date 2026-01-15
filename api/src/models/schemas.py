"""Pydantic schemas for API endpoints."""
from typing import Any, Optional
from pydantic import BaseModel, Field


# Health Check
class HealthResponse(BaseModel):
    """Health check response."""
    status: str = "ok"
    timestamp: int


# Providers
class ProviderStats(BaseModel):
    """Provider statistics."""
    avg_latency_ms: int
    success_rate: float
    current_block: int


class Provider(BaseModel):
    """Provider information."""
    id: int
    name: str
    url: str
    status: str
    score: int
    supports_traces: bool
    last_probe_at: Optional[int] = None
    stats: Optional[ProviderStats] = None


class ProvidersResponse(BaseModel):
    """Providers health response."""
    providers: list[Provider]
    history: Optional[dict[str, Any]] = None
    generated_at: int


# Contracts
class CreateContractRequest(BaseModel):
    """Request to create a contract."""
    address: str = Field(..., min_length=42, max_length=42)
    name: str = Field(..., min_length=1, max_length=128)
    tags: list[str] = Field(default_factory=list)
    abi_json: Optional[list[dict[str, Any]]] = None


class Contract(BaseModel):
    """Contract information."""
    id: int
    address: str
    name: str
    tags: list[str]
    has_abi: bool
    is_watched: bool
    created_at: int


class ContractResponse(BaseModel):
    """Contract response."""
    contract: Contract
