def main() -> None:
    from .nix import install

    install()

    import asyncio

    from .cli import amain

    asyncio.run(amain())
