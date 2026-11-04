"""Serve this co-worker's read-only goal exchange."""
from mn_sdk.blueprint.services import run_peer_exchange

if __name__ == "__main__":
    run_peer_exchange(goal_id="bibblio-marketing")
