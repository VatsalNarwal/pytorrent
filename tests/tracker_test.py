import asyncio
import logging
from pytorrent.core.torrent import Torrent
from pytorrent.core.tracker import TrackerManager

logging.basicConfig(level=logging.INFO)

async def test_tracker():
    # Load the torrent file
    t = Torrent('ubuntu.torrent')
    print(t)
    print(f"Info Hash: {t.info_hash.hex()}")
    
    # Connect to tracker
    tracker = TrackerManager(t)
    peers = await tracker.get_peers()
    
    print("\n--- Peers Found ---")
    for ip, port in peers[:10]: # Print first 10
        print(f"{ip}:{port}")

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(test_tracker())