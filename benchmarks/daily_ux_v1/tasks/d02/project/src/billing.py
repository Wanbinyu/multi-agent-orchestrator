def charge(amount: int) -> int:
    if amount < 0:
        raise ValueError("negative")
    return amount
