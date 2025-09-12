def main() -> None:
    from .nix import install, loop_factory

    install()

    import asyncio

    from .cli import amain

    asyncio.run(amain(), loop_factory=loop_factory())
