import os
from pytorrent.core.torrent import Torrent
from pytorrent.core.pieces import PieceManager

# 1. Setup
t = Torrent('ubuntu.torrent')
manager = PieceManager(t)

# Create a dummy file for the download (filled with zeros)
# Only making it big enough for the first piece to test
with open(t.name, 'wb') as f:
    f.write(b'\x00' * t.piece_length * 2)

print(f"Created dummy file: {t.name}")
print(f"Total Pieces Needed: {len(manager.needed)}")

# 2. Simulate a Peer
# Let's say we have a peer who has EVERYTHING (all 1s)
# Bitfield can be a list of booleans
peer_bitfield = [1] * len(t.pieces)

# 3. Request a Block
print("\n--- Requesting Block ---")
result = manager.get_next_block(peer_bitfield)
if result:
    piece, offset, length = result
    print(f"Manager requested: Piece {piece.index}, Offset {offset}, Length {length}")
    
    # 4. Simulate Receiving Data
    # We'll fake the data (it won't pass hash check, but logic will run)
    fake_data = b'X' * length
    manager.block_received(piece.index, offset, fake_data)
    
    print(f"Piece Status: {piece.blocks[0]['status']} (2 means Retrieved)")
else:
    print("Manager requested nothing.")
    
# Cleanup
os.remove(t.name)