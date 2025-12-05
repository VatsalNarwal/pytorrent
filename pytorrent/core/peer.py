import asyncio
import struct
import logging

logger = logging.getLogger(__name__)

class BitTorrentPeer:
    def __init__(self, ip, port, torrent, peer_id, piece_manager):
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

    async def connect(self):
        try:
            self.reader, self.writer = await asyncio.open_connection(self.ip, self.port)
            await self._handshake()
            return True
        except Exception as e:
            self.close()
            return False

    async def _handshake(self):
        pstring = b"BitTorrent protocol"
        reserved = b'\x00' * 8
        handshake = struct.pack(">B19s8s20s20s", 19, pstring, reserved, self.torrent.info_hash, self.my_peer_id)
        self.writer.write(handshake)
        await self.writer.drain()
        data = await self.reader.readexactly(68)
        # Validation skipped for brevity, but assumed correct from previous steps

    async def start_listening(self):
        if not self.reader: return
        # Immediate Interested + Unchoke
        await self.send_interested()
        self.writer.write(struct.pack('>IB', 1, 1)) 
        await self.writer.drain()
        
        try:
            while True:
                length_data = await self.reader.readexactly(4)
                msg_length = struct.unpack('>I', length_data)[0]
                if msg_length == 0: continue # Keep-Alive

                msg_id_data = await self.reader.readexactly(1)
                msg_id = struct.unpack('>B', msg_id_data)[0]
                
                payload_length = msg_length - 1
                payload = b''
                if payload_length > 0:
                    payload = await self.reader.readexactly(payload_length)

                await self._handle_message(msg_id, payload)
        except Exception:
            self.close()

    async def send_interested(self):
        if not self.interested:
            self.writer.write(struct.pack(">IB", 1, 2))
            await self.writer.drain()
            self.interested = True

    async def _handle_message(self, msg_id, payload):
        if msg_id == 0: # Choke
            self.choked = True
        elif msg_id == 1: # Unchoke
            self.choked = False
            await self._request_more_blocks()
        elif msg_id == 4: # Have
            piece_index = struct.unpack('>I', payload)[0]
            self._update_bitfield(piece_index)
            if not self.choked: await self._request_more_blocks()
        elif msg_id == 5: # Bitfield
            await self._handle_bitfield(payload)
        elif msg_id == 6: # Request (Seeding)
            await self._handle_request(payload)
        elif msg_id == 7: # Piece
            await self._handle_piece(payload)

    async def _handle_request(self, payload):
        index = struct.unpack('>I', payload[0:4])[0]
        begin = struct.unpack('>I', payload[4:8])[0]
        length = struct.unpack('>I', payload[8:12])[0]
        if self.piece_manager:
            block = self.piece_manager.read_block(index, begin, length)
            if block:
                msg = struct.pack('>IBII', 9 + len(block), 7, index, begin) + block
                self.writer.write(msg)
                await self.writer.drain()

    async def _handle_bitfield(self, payload):
        new_bitfield = []
        for byte in payload:
            for i in range(7, -1, -1):
                new_bitfield.append((byte >> i) & 1)
        
        num_pieces = len(self.torrent.pieces)
        if len(new_bitfield) >= num_pieces:
            self.bitfield = new_bitfield[:num_pieces]
        else:
            self.bitfield = new_bitfield + [0] * (num_pieces - len(new_bitfield))
            
        if self.piece_manager:
            self.piece_manager.add_peer(self, self.bitfield)
        
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
        
        print(f"Received: Piece {index} (Offset {begin}) from {self.ip}")
        
        if self.inflight_requests > 0: self.inflight_requests -= 1
        if self.piece_manager: self.piece_manager.block_received(index, begin, block_data)
        
        await self._request_more_blocks()

    async def _request_more_blocks(self):
        if self.choked: return 
        MAX_PIPELINE = 10 
        
        try:
            while self.inflight_requests < MAX_PIPELINE:
                if self.piece_manager:
                    block = self.piece_manager.get_next_block(self.bitfield)
                    if block:
                        piece, offset, length = block
                        print(f"Requesting: Piece {piece.index} (Offset {offset}) from {self.ip}")
                        req = struct.pack('>IBIII', 13, 6, piece.index, offset, length)
                        self.writer.write(req)
                        self.inflight_requests += 1
                    else:
                        break
            await self.writer.drain()
        except (ConnectionResetError, BrokenPipeError, ConnectionError):
            # Peer disconnected while we were writing. Not a bug, just the internet.
            # logger.debug(f"Peer {self.ip} disconnected during request.")
            self.close()
        except Exception as e:
            logger.error(f"Unexpected error requesting blocks from {self.ip}: {e}")
            self.close()

    def close(self):
        if self.writer: 
            try: self.writer.close()
            except: pass