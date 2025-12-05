import asyncio
import struct
import logging
import random
from pytorrent.utils import crypto

logger = logging.getLogger(__name__)

class BitTorrentPeer:
    def __init__(self, ip, port, torrent, peer_id, piece_manager, encryption_enabled):
        self.ip = ip
        self.port = port
        self.torrent = torrent
        self.my_peer_id = peer_id
        self.piece_manager = piece_manager
        self.reader = None
        self.writer = None
        self.choked = True       
        self.interested = False   
        self.bitfield = [0] * len(torrent.pieces)
        self.inflight_requests = 0
        self.encryption_enabled = encryption_enabled
        
        # Encryption State
        self.rc4_encrypt = None
        self.rc4_decrypt = None

    async def connect(self):
        try:
            # OPTION 1: Encryption Requested
            if self.encryption_enabled:
                try:
                    # Attempt MSE Handshake
                    self.reader, self.writer = await asyncio.open_connection(self.ip, self.port)
                    if await self._mse_handshake():
                        await self._handshake()
                        return True
                except Exception:
                    self.close()
            
            # OPTION 2: Plaintext (Default or Fallback)
            self.reader, self.writer = await asyncio.open_connection(self.ip, self.port)
            
            self.rc4_encrypt = None
            self.rc4_decrypt = None
            
            await self._handshake()
            return True
        except Exception as e:
            self.close()
            return False

    async def _mse_handshake(self):
        """
        # Performs the Diffie-Hellman Key Exchange (BEP 8).
        """
        try:
            # 1. Generate our keys
            dh = crypto.DiffieHellman()
            my_pub_bytes = dh.public_key.to_bytes(96, 'big')
            
            # 2. Send Public Key + Random Padding (0-512 bytes)
            # This padding prevents traffic analysis
            pad_a = bytes([random.randint(0, 255) for _ in range(random.randint(0, 512))])
            self.writer.write(my_pub_bytes + pad_a)
            await self.writer.drain()
            
            # 3. Read Peer's Public Key
            # We don't know exactly how much padding they sent, but the DH key is 96 bytes.
            # However, simpler implementations assume peer sends Key immediately.
            # Real-world peers might send Key + Pad. We'll try to read 96 bytes first.
            
            # NOTE: Blocking here is dangerous if peer isn't encrypted.
            # We set a short timeout.
            peer_pub_bytes = await asyncio.wait_for(self.reader.readexactly(96), timeout=5.0)
            
            # 4. Compute Shared Secret
            s_bytes = dh.compute_secret(peer_pub_bytes)
            
            # 5. Initialize RC4 Engines
            enc_key, dec_key = crypto.get_encryption_keys(s_bytes, self.torrent.info_hash)
            self.rc4_encrypt = crypto.RC4(enc_key)
            self.rc4_decrypt = crypto.RC4(dec_key)
            
            # 6. Synchronization Step (The 'Crypto Select' phase)
            # We must verify we can read their padding until we find the sync sequence.
            # For simplicity in V1, we assume minimal padding from peer or skip sync 
            # (Strictly speaking, we should read until we verify protocol, but that's complex).
            # We will just proceed to encrypting the Handshake.
            
            # logger.info(f"MSE Encryption established with {self.ip}")
            return True
            
        except (asyncio.TimeoutError, ValueError):
            # Peer doesn't support encryption or timed out
            # In a full client, we would fall back to plain TCP here.
            # logger.debug(f"{self.ip} does not support encryption.")
            return False

    async def _send(self, data):
        """Helper to encrypt data before sending if encryption is active"""
        if self.rc4_encrypt:
            data = self.rc4_encrypt.crypt(data)
        self.writer.write(data)
        await self.writer.drain()

    async def _read(self, n):
        """Helper to decrypt data after reading if encryption is active"""
        data = await self.reader.readexactly(n)
        if self.rc4_decrypt:
            data = self.rc4_decrypt.crypt(data)
        return data

    async def _handshake(self):
        pstring = b"BitTorrent protocol"
        reserved = b'\x00' * 8
        
        # Use _send instead of writer.write
        handshake = struct.pack(">B19s8s20s20s", 19, pstring, reserved, self.torrent.info_hash, self.my_peer_id)
        await self._send(handshake)
        
        # Use _read instead of reader.readexactly
        data = await self._read(68)
        
        # Verification (Same as before)
        re_len, re_pstr, re_reserved, re_info_hash, re_peer_id = struct.unpack(">B19s8s20s20s", data)
        if re_info_hash != self.torrent.info_hash:
            raise ValueError("Info hash mismatch")

    async def start_listening(self):
        if not self.reader: return
        await self.send_interested()
        await self._send(struct.pack('>IB', 1, 1)) # Unchoke
        
        try:
            while True:
                # Use _read for everything
                length_data = await self._read(4)
                msg_length = struct.unpack('>I', length_data)[0]
                if msg_length == 0: continue 

                msg_id_data = await self._read(1)
                msg_id = struct.unpack('>B', msg_id_data)[0]
                
                payload_length = msg_length - 1
                payload = b''
                if payload_length > 0:
                    payload = await self._read(payload_length)

                await self._handle_message(msg_id, payload)
        except Exception as e:
            # logger.error(f"Error {e}")
            self.close()

    async def send_interested(self):
        if not self.interested:
            await self._send(struct.pack(">IB", 1, 2))
            self.interested = True

    async def _handle_message(self, msg_id, payload):
        if msg_id == 0: self.choked = True
        elif msg_id == 1: 
            self.choked = False
            await self._request_more_blocks()
        elif msg_id == 4: 
            piece_index = struct.unpack('>I', payload)[0]
            self._update_bitfield(piece_index)
            if not self.choked: await self._request_more_blocks()
        elif msg_id == 5: await self._handle_bitfield(payload)
        elif msg_id == 6: await self._handle_request(payload)
        elif msg_id == 7: await self._handle_piece(payload)

    async def _handle_request(self, payload):
        index = struct.unpack('>I', payload[0:4])[0]
        begin = struct.unpack('>I', payload[4:8])[0]
        length = struct.unpack('>I', payload[8:12])[0]
        if self.piece_manager:
            block = self.piece_manager.read_block(index, begin, length)
            if block:
                msg = struct.pack('>IBII', 9 + len(block), 7, index, begin) + block
                await self._send(msg)

    async def _handle_bitfield(self, payload):
        new_bitfield = []
        for byte in payload:
            for i in range(7, -1, -1):
                new_bitfield.append((byte >> i) & 1)
        num = len(self.torrent.pieces)
        self.bitfield = new_bitfield[:num] + ([0]*(num-len(new_bitfield)) if len(new_bitfield) < num else [])
        if self.piece_manager: self.piece_manager.add_peer(self, self.bitfield)
        await self.send_interested()
        if not self.choked: await self._request_more_blocks()

    def _update_bitfield(self, piece_index):
        if piece_index < len(self.bitfield):
            self.bitfield[piece_index] = 1
            if self.piece_manager: self.piece_manager.update_peer(self, piece_index)

    async def _handle_piece(self, payload):
        index = struct.unpack('>I', payload[0:4])[0]
        begin = struct.unpack('>I', payload[4:8])[0]
        block_data = payload[8:]
        status = "[HYBRID]" if self.rc4_decrypt else "[PLAINTEXT]"
        print(f"Received: Piece {index} (Offset {begin}) from {self.ip} {status}")
        if self.inflight_requests > 0: self.inflight_requests -= 1
        if self.piece_manager: self.piece_manager.block_received(index, begin, block_data)
        await self._request_more_blocks()

    async def _request_more_blocks(self):
        if self.choked: return 
        try:
            while self.inflight_requests < 10:
                if self.piece_manager:
                    block = self.piece_manager.get_next_block(self.bitfield)
                    if block:
                        piece, offset, length = block
                        print(f"Requesting: Piece {piece.index} from {self.ip}")
                        req = struct.pack('>IBIII', 13, 6, piece.index, offset, length)
                        await self._send(req)
                        self.inflight_requests += 1
                    else: break
        except Exception: self.close()

    def close(self):
        if self.writer: 
            try: self.writer.close()
            except: pass