import math
import logging
import hashlib
import time
import os
from collections import defaultdict

BLOCK_SIZE = 16384 

logger = logging.getLogger(__name__)

class Piece:
    def __init__(self, index, piece_length, hash_value):
        self.index = index
        self.length = piece_length
        self.hash = hash_value
        self.is_full = False
        self.data = b''
        self.num_blocks = math.ceil(self.length / BLOCK_SIZE)
        self.blocks = []
        
        for i in range(self.num_blocks):
            offset = i * BLOCK_SIZE
            length = min(BLOCK_SIZE, self.length - offset)
            self.blocks.append({
                'offset': offset,
                'length': length,
                'status': 0, 
                'data': None,
                'last_requested': 0 
            })

    def add_block(self, offset, data):
        for block in self.blocks:
            if block['offset'] == offset:
                block['status'] = 2 
                block['data'] = data
                break
        
        if all(b['status'] == 2 for b in self.blocks):
            self._assemble()
            return True
        return False

    def _assemble(self):
        self.blocks.sort(key=lambda b: b['offset'])
        self.data = b''.join(b['data'] for b in self.blocks)
        self.is_full = True

    def validate(self):
        calculated_hash = hashlib.sha1(self.data).digest()
        return calculated_hash == self.hash
    
    def reset(self):
        self.data = b''
        self.is_full = False
        for block in self.blocks:
            block['status'] = 0
            block['data'] = None
            block['last_requested'] = 0

class PieceManager:
    def __init__(self, torrent):
        self.torrent = torrent
        self.peers = {} 
        self.needed = []      
        self.in_progress = [] 
        self.finished = []    
        self._init_pieces()

    def _init_pieces(self):
        num_pieces = len(self.torrent.pieces)
        for i in range(num_pieces):
            if i == num_pieces - 1:
                remainder = self.torrent.total_length % self.torrent.piece_length
                length = remainder if remainder else self.torrent.piece_length
            else:
                length = self.torrent.piece_length
            p = Piece(i, length, self.torrent.pieces[i])
            self.needed.append(p)
        logger.info(f"PieceManager initialized with {len(self.needed)} pieces")

    def add_peer(self, peer_object, bitfield):
        self.peers[peer_object] = bitfield
    
    def update_peer(self, peer_object, piece_index):
        if peer_object in self.peers:
            self.peers[peer_object][piece_index] = 1
            
    def remove_peer(self, peer_object):
        if peer_object in self.peers:
            del self.peers[peer_object]

    def check_disk_integrity(self):
        logger.info("Starting integrity check on existing files...")
        try:
            for piece in self.needed[:]:
                # We reuse read_block logic, but read the WHOLE piece
                data = self._read_from_files(piece.index, 0, piece.length)
                
                if data and len(data) == piece.length:
                    if hashlib.sha1(data).digest() == piece.hash:
                        piece.data = None 
                        piece.is_full = True
                        self.needed.remove(piece)
                        self.finished.append(piece)
                        
            logger.info(f"Integrity Check: Resuming with {len(self.finished)} pieces finished.")
        except Exception as e:
            logger.error(f"Integrity check failed: {e}")

    def get_next_block(self, peer_bitfield):
        # 1. Finish In-Progress (Always top priority to close open blocks)
        for piece in self.in_progress:
            if peer_bitfield[piece.index]:
                for block in piece.blocks:
                    if block['status'] == 0:
                        block['status'] = 1
                        block['last_requested'] = time.time()
                        return (piece, block['offset'], block['length'])

        # 2. Rarest First Strategy
        # Filter: Find all pieces this peer actually has
        candidates = [p for p in self.needed if peer_bitfield[p.index]]
        
        if not candidates:
            return None # Peer has nothing we want

        # Helper to calculate rarity (how many peers have this piece)
        def get_rarity(piece):
            count = 0
            for peer_bf in self.peers.values():
                if peer_bf[piece.index]:
                    count += 1
            return count

        # Sort by Rarity (Ascending: rarest pieces first)
        candidates.sort(key=get_rarity)
        
        # Pick the rarest
        piece = candidates[0]
        
        self.needed.remove(piece)
        self.in_progress.append(piece)
        
        block = piece.blocks[0]
        block['status'] = 1
        block['last_requested'] = time.time()
        return (piece, block['offset'], block['length'])

    def recover_stalled_blocks(self):
        TIMEOUT = 5.0 
        now = time.time()
        for piece in self.in_progress:
            for block in piece.blocks:
                if block['status'] == 1 and (now - block['last_requested']) > TIMEOUT:
                    block['status'] = 0 
                    block['last_requested'] = 0

    def block_received(self, piece_index, offset, data):
        piece = next((p for p in self.in_progress if p.index == piece_index), None)
        if not piece: return
        
        is_complete = piece.add_block(offset, data)
        if is_complete:
            if piece.validate():
                self.in_progress.remove(piece)
                self.finished.append(piece)
                self._write_to_disk(piece)
                logger.info(f"Piece {piece.index} downloaded and verified.")
            else:
                logger.warning(f"Piece {piece.index} failed hash check.")
                piece.reset()
                self.in_progress.remove(piece)
                self.needed.insert(0, piece) 

    # --- MULTI-FILE WRITE LOGIC ---
    def _write_to_disk(self, piece):
        piece_start = piece.index * self.torrent.piece_length
        piece_end = piece_start + piece.length
        
        # We assume piece.data holds the full binary blob
        # We need to slice this blob and write it to potentially multiple files
        
        for file in self.torrent.files:
            file_start = file['offset']
            file_end = file_start + file['length']
            
            # Check overlap
            if max(piece_start, file_start) < min(piece_end, file_end):
                # Calculate write range in the global stream
                write_global_start = max(piece_start, file_start)
                write_global_end = min(piece_end, file_end)
                write_len = write_global_end - write_global_start
                
                # Calculate offsets
                file_seek_pos = write_global_start - file_start
                piece_buffer_offset = write_global_start - piece_start
                
                # Slice data
                data_slice = piece.data[piece_buffer_offset : piece_buffer_offset + write_len]
                
                try:
                    with open(file['path'], 'r+b') as f:
                        f.seek(file_seek_pos)
                        f.write(data_slice)
                except Exception as e:
                    logger.error(f"Failed to write to {file['path']}: {e}")
        
        piece.data = None

    # --- MULTI-FILE READ LOGIC (Seeding & Integrity) ---
    def _read_from_files(self, piece_index, offset, length):
        """Internal helper to read across file boundaries"""
        global_start = (piece_index * self.torrent.piece_length) + offset
        global_end = global_start + length
        
        buffer = b''
        
        for file in self.torrent.files:
            file_start = file['offset']
            file_end = file_start + file['length']
            
            if max(global_start, file_start) < min(global_end, file_end):
                read_global_start = max(global_start, file_start)
                read_global_end = min(global_end, file_end)
                read_len = read_global_end - read_global_start
                
                file_seek_pos = read_global_start - file_start
                
                try:
                    with open(file['path'], 'rb') as f:
                        f.seek(file_seek_pos)
                        chunk = f.read(read_len)
                        buffer += chunk
                except OSError:
                    return None # File missing or error
                    
        return buffer if len(buffer) == length else None

    def read_block(self, piece_index, offset, length):
        return self._read_from_files(piece_index, offset, length)