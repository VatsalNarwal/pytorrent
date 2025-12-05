import hashlib
import math
import logging
import os
from pytorrent.utils import bencoder

class Torrent:
    def __init__(self, filename):
        self.filename = filename
        self.announce_url = None
        self.announce_list = []
        self.info_hash = None
        self.piece_length = 0
        self.pieces = [] 
        self.total_length = 0
        self.name = None
        self.files = []  
        
        self._parse()

    def _parse(self):
        with open(self.filename, 'rb') as f:
            meta_info = bencoder.decode(f.read())
        
        self.announce_url = meta_info[b'announce'].decode('utf-8')
        self.announce_list = [self.announce_url]
        
        if b'announce-list' in meta_info:
            for tier in meta_info[b'announce-list']:
                for url in tier:
                    self.announce_list.append(url.decode('utf-8'))
        
        self.announce_list = list(set(self.announce_list))
        
        info = meta_info[b'info']
        raw_info = bencoder.encode(info)
        self.info_hash = hashlib.sha1(raw_info).digest()
        
        self.name = info[b'name'].decode('utf-8')
        self.piece_length = info[b'piece length']
        
        pieces_blob = info[b'pieces']
        for i in range(0, len(pieces_blob), 20):
            self.pieces.append(pieces_blob[i : i+20])
            
        # --- MULTI-FILE PARSING ---
        current_offset = 0
        if b'files' in info:
            # Multi-file mode
            for file_data in info[b'files']:
                length = file_data[b'length']
                path_parts = [p.decode('utf-8') for p in file_data[b'path']]
                path = os.path.join(self.name, *path_parts) # Join with root folder
                
                self.files.append({
                    'path': path,
                    'length': length,
                    'offset': current_offset # Global start position
                })
                current_offset += length
            self.total_length = current_offset
        else:
            # Single-file mode
            self.total_length = info[b'length']
            self.files.append({
                'path': self.name,
                'length': self.total_length,
                'offset': 0
            })
            
    def __str__(self):
        return f"Torrent: {self.name} containing {len(self.files)} files. Total: {self.total_length/1024/1024:.2f} MB"