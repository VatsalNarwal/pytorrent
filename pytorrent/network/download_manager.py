import asyncio
import logging
import os
from pytorrent.core.torrent import Torrent
from pytorrent.core.tracker import TrackerManager
from pytorrent.core.pieces import PieceManager
from pytorrent.core.peer import BitTorrentPeer

logger = logging.getLogger(__name__)

class DownloadManager:
    def __init__(self, torrent_file, encryption_enabled=False):
        self.torrent = Torrent(torrent_file)
        self.tracker = TrackerManager(self.torrent)
        self.piece_manager = PieceManager(self.torrent)
        self.peers = [] 
        self.encryption_enabled = encryption_enabled
        
    async def start(self):
        print(f"Starting download for: {self.torrent.name}")
        print(f"Encryption: {'ENABLED (Hybrid)' if self.encryption_enabled else 'DISABLED (Plaintext)'}")
        
        # --- MULTI-FILE INITIALIZATION ---
        # 1. Ensure directories exist
        # 2. Pre-allocate empty files
        
        files_exist = True
        
        for file in self.torrent.files:
            path = file['path']
            
            # Create subdirectories if needed
            folder = os.path.dirname(path)
            if folder and not os.path.exists(folder):
                os.makedirs(folder)
                
            if not os.path.exists(path):
                files_exist = False
                print(f"Creating file: {path} ({file['length'] // 1024} KB)")
                with open(path, 'wb') as f:
                    # Pre-allocate sparse file
                    f.seek(file['length'] - 1)
                    f.write(b'\0')
        
        # 3. Check Integrity
        if files_exist:
            print("Found existing files. Verifying integrity...")
            self.piece_manager.check_disk_integrity()
            
        peer_list = await self.tracker.get_peers()
        peer_list = list(set(peer_list)) 
        print(f"Unique peers found: {len(peer_list)}")
        
        MAX_PEERS = 50
        for ip, port in peer_list[:MAX_PEERS]:
            peer = BitTorrentPeer(
                ip, port, self.torrent, 
                self.tracker.peer_id, 
                self.piece_manager,
                encryption_enabled=self.encryption_enabled
            )
            self.peers.append(peer)
            asyncio.ensure_future(self.full_peer_lifecycle(peer))
            
        await self.monitor_download()
        
    async def full_peer_lifecycle(self, peer):
        try:
            if await peer.connect():
                self.piece_manager.add_peer(peer, peer.bitfield)
                await peer.start_listening()
        except: pass
        finally:
            self.piece_manager.remove_peer(peer)
            
    async def monitor_download(self):
        total_pieces = len(self.torrent.pieces)
        while True:
            self.piece_manager.recover_stalled_blocks()
            
            for peer in self.peers:
                if not peer.choked:
                    asyncio.ensure_future(peer._request_more_blocks())
            
            finished = len(self.piece_manager.finished)
            progress = (finished / total_pieces) * 100
            active = sum(1 for p in self.peers if not p.choked)
            
            if finished < total_pieces:
                print(f"Downloading: {progress:.2f}% | Active: {active} | Pieces: {finished}/{total_pieces}")
            else:
                print(f"Seeding... (100%) | Connected Peers: {len(self.peers)}")
            
            await asyncio.sleep(2)