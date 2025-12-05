import aiohttp
import asyncio
import struct
import socket
import logging
import random
import urllib.parse
from pytorrent.utils import bencoder

logger = logging.getLogger(__name__)

class UdpTrackerClient(asyncio.DatagramProtocol):
    def __init__(self):
        self.transport = None
        self.response_future = None

    def connection_made(self, transport):
        self.transport = transport

    def datagram_received(self, data, addr):
        if self.response_future and not self.response_future.done():
            self.response_future.set_result(data)

    def error_received(self, exc):
        if self.response_future and not self.response_future.done():
            self.response_future.set_exception(exc)

    def connection_lost(self, exc):
        if self.response_future and not self.response_future.done():
            self.response_future.set_exception(ConnectionError("Connection lost"))

class TrackerManager:
    def __init__(self, torrent):
        self.torrent = torrent
        self.peer_id = self._generate_peer_id()
        self.peers = [] # List of (ip, port)
        self.interval = 0

    def _generate_peer_id(self):
        prefix = b'-PT0001-'
        random_part = bytes([random.randint(0, 255) for _ in range(12)])
        return prefix + random_part

    async def get_peers(self):
        """
        Connects to HTTP and UDP trackers to get peers.
        """
        MAX_TRACKERS = 5
        # trackers_to_try = self.torrent.announce_list[:MAX_TRACKERS]
        trackers_to_try = self.torrent.announce_list
        logger.info(f"Announce list has {len(self.torrent.announce_list)} trackers.")

        headers = {'User-Agent': 'Transmission/2.94'}
        connector = aiohttp.TCPConnector(limit=10, force_close=True)
        
        async with aiohttp.ClientSession(connector=connector, headers=headers) as http_session:
            for tracker_url in trackers_to_try:
                if tracker_url.startswith('udp'):
                    await self._scrape_udp(tracker_url)
                elif tracker_url.startswith('http'):
                    await self._scrape_http(tracker_url, http_session)
                
                if len(self.peers) > 50:
                    break
        
        return self.peers

    async def _scrape_http(self, url, session):
        try:
            params = {
                'info_hash': self.torrent.info_hash,
                'peer_id': self.peer_id,
                'port': 6881,
                'uploaded': 0, 'downloaded': 0, 
                'left': self.torrent.total_length,
                'compact': 1, 'event': 'started'
            }
            url_params = urllib.parse.urlencode(params)
            full_url = f"{url}?{url_params}"
            
            logger.info(f"Connecting to HTTP tracker: {url}")
            async with session.get(full_url, timeout=5) as response:
                if response.status == 200:
                    data = await response.read()
                    self._parse_tracker_response(data)
        except Exception as e:
            logger.error(f"HTTP Tracker {url} failed: {repr(e)}")

    # CRITICAL: This MUST be 'async def' to use 'await' inside
    async def _scrape_udp(self, url):
        """UDP Announce (BEP 15)"""
        logger.info(f"Connecting to UDP tracker: {url}")
        
        parsed = urllib.parse.urlparse(url)
        try:
            ip = socket.gethostbyname(parsed.hostname)
            port = parsed.port
        except Exception as e:
            logger.error(f"UDP DNS resolution failed for {url}: {e}")
            return

        # Python 3.6 compatible loop retrieval
        loop = asyncio.get_event_loop()
        
        # 1. Create UDP Transport
        try:
            transport, protocol = await loop.create_datagram_endpoint(
                lambda: UdpTrackerClient(),
                remote_addr=(ip, port)
            )
        except Exception as e:
            logger.error(f"UDP Connection failed: {e}")
            return

        try:
            # --- STEP 1: CONNECT REQUEST ---
            transaction_id = random.randint(0, 0xFFFFFFFF)
            # Magic (0x41727101980) + Action (0) + TransID
            req = struct.pack("!QII", 0x41727101980, 0, transaction_id)
            
            transport.sendto(req)
            
            # Wait for response (Timeout 5s)
            protocol.response_future = loop.create_future()
            # Passing timeout as positional arg to avoid any syntax ambiguity
            data = await asyncio.wait_for(protocol.response_future, 10)
            
            if len(data) < 16: raise ValueError("UDP response too short")
            action, res_transaction_id, connection_id = struct.unpack("!IIQ", data[:16])
            
            if res_transaction_id != transaction_id: raise ValueError("Transaction ID mismatch")
            if action != 0: raise ValueError(f"UDP Error Action: {action}")

            # --- STEP 2: ANNOUNCE REQUEST ---
            transaction_id = random.randint(0, 0xFFFFFFFF)
            key = random.randint(0, 0xFFFFFFFF)
            
            req = struct.pack("!QII", connection_id, 1, transaction_id)
            req += self.torrent.info_hash
            req += self.peer_id
            req += struct.pack("!QQQIIIiH", 
                0, 0, self.torrent.total_length, 
                0, 0, key, -1, 6881 
            )
            
            transport.sendto(req)
            
            protocol.response_future = loop.create_future()
            data = await asyncio.wait_for(protocol.response_future, 5)
            
            if len(data) < 20: raise ValueError("UDP announce response too short")
            action, res_transaction_id, interval, leechers, seeders = struct.unpack("!IIIII", data[:20])
            
            if res_transaction_id != transaction_id: raise ValueError("Transaction ID mismatch")
            
            peers_data = data[20:]
            new_peers = self._parse_compact_peers(peers_data)
            self.peers.extend(new_peers)
            logger.info(f"UDP Tracker returned {len(new_peers)} peers (Seeders: {seeders})")

        except asyncio.TimeoutError:
            logger.error(f"UDP Tracker {url} timed out")
        except Exception as e:
            logger.error(f"UDP Tracker {url} failed: {repr(e)}")
        finally:
            transport.close()

    def _parse_tracker_response(self, data):
        try:
            response = bencoder.decode(data)
            peers_data = response.get(b'peers')
            if peers_data:
                if isinstance(peers_data, bytes):
                    self.peers.extend(self._parse_compact_peers(peers_data))
                elif isinstance(peers_data, list):
                    for p in peers_data:
                        ip = p[b'ip'].decode('utf-8')
                        port = p[b'port']
                        self.peers.append((ip, port))
            logger.info(f"HTTP Tracker returned peers. Total now: {len(self.peers)}")
        except Exception:
            pass

    def _parse_compact_peers(self, data):
        peers = []
        num_peers = len(data) // 6
        for i in range(num_peers):
            offset = i * 6
            try:
                ip_int, port = struct.unpack_from("!IH", data, offset)
                ip_str = socket.inet_ntoa(struct.pack("!I", ip_int))
                peers.append((ip_str, port))
            except: pass
        return peers