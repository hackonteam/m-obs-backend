"""Error decoding for transaction reverts."""
from typing import Optional
from eth_abi import decode
from eth_utils import to_hex


# Standard error signatures
ERROR_SIGNATURES = {
    "0x08c379a0": "Error(string)",
    "0x4e487b71": "Panic(uint256)",
}

# Panic codes mapping
PANIC_CODES = {
    0x01: "Assertion failed",
    0x11: "Arithmetic overflow/underflow",
    0x12: "Division by zero",
    0x21: "Invalid enum value",
    0x31: "Pop on empty array",
    0x32: "Array index out of bounds",
    0x41: "Memory allocation failed",
    0x51: "Zero-initialized function pointer",
}


def extract_error_signature(error_data: str) -> Optional[str]:
    """Extract error signature (first 4 bytes) from revert data."""
    if not error_data or len(error_data) < 10:
        return None
    
    # Ensure 0x prefix
    if not error_data.startswith("0x"):
        error_data = f"0x{error_data}"
    
    # Extract first 4 bytes (8 hex chars + 0x)
    return error_data[:10].lower()


def decode_error(error_data: str) -> tuple[Optional[str], Optional[dict]]:
    """
    Decode error data into human-readable message and parameters.
    
    Args:
        error_data: Hex-encoded revert data
    
    Returns:
        Tuple of (decoded_message, params_dict)
    """
    if not error_data:
        return "Unknown revert", None
    
    signature = extract_error_signature(error_data)
    
    if not signature:
        return "Unknown revert", None
    
    # Decode standard Error(string)
    if signature == "0x08c379a0":
        try:
            # Remove signature (first 4 bytes)
            data_bytes = bytes.fromhex(error_data[10:])
            # Decode as string
            decoded = decode(["string"], data_bytes)
            message = decoded[0]
            return message, {"message": message}
        except Exception:
            return "Error(string)", None
    
    # Decode Panic(uint256)
    elif signature == "0x4e487b71":
        try:
            # Remove signature
            data_bytes = bytes.fromhex(error_data[10:])
            # Decode as uint256
            decoded = decode(["uint256"], data_bytes)
            panic_code = decoded[0]
            message = PANIC_CODES.get(panic_code, f"Panic({panic_code})")
            return message, {"code": panic_code}
        except Exception:
            return "Panic(uint256)", None
    
    # Unknown custom error
    else:
        return f"Custom error {signature}", None


def decode_with_abi(error_data: str, abi_json: list) -> tuple[Optional[str], Optional[dict]]:
    """
    Decode error using contract ABI.
    
    Args:
        error_data: Hex-encoded revert data
        abi_json: Contract ABI as list of dicts
    
    Returns:
        Tuple of (decoded_message, params_dict)
    """
    # TODO: Implement ABI-based error decoding
    # For now, fall back to standard decoding
    return decode_error(error_data)
