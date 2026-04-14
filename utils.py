import hashlib

def generate_error_fingerprint(error: str) -> str:
    """
    Generate a stable fingerprint for an error string.
    """

    normalized_error = error.lower().strip()

    # Remove newlines (basic normalization)
    normalized_error = normalized_error.replace("\n", " ")

    return hashlib.md5(normalized_error.encode()).hexdigest()