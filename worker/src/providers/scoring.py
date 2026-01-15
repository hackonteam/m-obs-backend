"""Provider health scoring algorithm."""
from typing import Optional


def calculate_score(
    latency_ms: Optional[int],
    consecutive_failures: int,
    block_lag: int,
) -> int:
    """
    Calculate provider health score (0-100).
    
    Args:
        latency_ms: Response latency (None if timeout)
        consecutive_failures: Number of consecutive failures
        block_lag: Blocks behind the leader
    
    Returns:
        Health score from 0 to 100
    """
    base_score = 100
    
    # Latency penalty
    if latency_ms is not None and latency_ms > 200:
        latency_penalty = min(30, (latency_ms - 200) / 50)
    else:
        latency_penalty = 0
    
    # Error penalty (25 points per failure, max 75)
    error_penalty = min(75, consecutive_failures * 25)
    
    # Block lag penalty (10 points per block behind)
    block_lag_penalty = block_lag * 10
    
    final_score = max(0, base_score - latency_penalty - error_penalty - block_lag_penalty)
    
    return int(final_score)


def score_to_status(score: int) -> str:
    """Convert score to status string."""
    if score > 80:
        return "healthy"
    elif score > 50:
        return "degraded"
    else:
        return "unhealthy"
