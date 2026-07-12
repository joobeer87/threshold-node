"""Run the local Threshold Node with privacy-first bind defaults."""

import uvicorn

from threshold.core.config import SETTINGS


def main() -> None:
    SETTINGS.validate_runtime()
    host, port = SETTINGS.bind_address()
    uvicorn.run("threshold.api.server:app", host=host, port=port)


if __name__ == "__main__":
    main()
