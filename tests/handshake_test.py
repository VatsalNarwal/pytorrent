import asyncio
import logging
from pytorrent.core.torrent import Torrent
from pytorrent.core.tracker import TrackerManager
from pytorrent.core.peer import BitTorrentPeer

logging.basicConfig(level=logging.INFO)

async def test_handshake():
    # 1. Load Torrent
    t = Torrent('ubuntu.torrent')
    print(f"Loaded: {t.name}")
    
    # 2. Get Peers from Tracker
    tracker = TrackerManager(t)
    peers = await tracker.get_peers()
    
    if not peers:
        print("No peers found. Check internet or tracker.")
        return

    print(f"Found {len(peers)} peers. Trying to handshake with the first few...")

    # 3. Try connecting to peers until one works
    # (Real peers are often offline, so we loop)
    for ip, port in peers[:10]:
        print(f"\n--- Attempting {ip}:{port} ---")
        
        # Dummy manager for now
        peer = BitTorrentPeer(ip, port, t, tracker.peer_id, piece_manager=None)
        
        try:
            await asyncio.wait_for(peer.connect(), timeout=5.0)
            print(">>> SUCCESS: Handshake complete! <<<")
            
            # NEW: Start listening for messages
            # We set a timeout of 10 seconds just to see if we get a Bitfield/Unchoke
            print("Listening for messages (10s)...")
            try:
                await asyncio.wait_for(peer.start_listening(), timeout=10.0)
            except asyncio.TimeoutError:
                print("Finished listening sample.")
            
            peer.close()
            break # Exit after one successful test            

        except Exception as e:
            print(f"Failed: {e}")
            peer.close()

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(test_handshake())