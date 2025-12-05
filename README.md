# PyTorrent: Asyncio BitTorrent Client

A lightweight, asynchronous BitTorrent client built from scratch in Python 3.6 using `asyncio`. 
Designed to demonstrate networking protocols, binary data manipulation, and concurrent I/O.

## 🚀 Features (Current Focus)
- [x] **Bencoding Parser/Encoder:** Full support for decoding `.torrent` files and encoding info dictionaries for hashing.
- [x] **Tracker Communication:** HTTP/UDP support to retrieve peer lists.
- [x] **Async Peer Protocol:** Event-driven TCP connections using `asyncio`.
- [x] **Piece Management:** Sequential download strategy with block assembly.
- [x] **Concurrency:** Simultaneous downloading from multiple peers.

## 🔮 Roadmap ([ADV] Features)
- [x] **Rarest-First Algorithm:** Optimized piece selection strategy.
- [x] **Pause/Resume:** State persistence for long downloads.
- [x] **Seeding:** Upload support for other peers.
- [ ] **Streaming Mode:** Prioritize sequential pieces for video playback.
- [ ] **AI Optimization:** Smart peer selection/scoring using simple heuristics or ML.
- [ ] **Privacy Mode:** SOCKS5 Proxy support to mask IP.
- [ ] **Protocol Obfuscation:** To bypass basic ISP throttling (MSE).
- [ ] **Content Safety:** ML-based classification of file metadata.
- [ ] **Reinforcement Learning:** Algorithm for peer selection.

## 😶‍🌫️**Further Details on [ADV]:**
* #### **Reinforcement Learning:**
  * Currently, clients mostly assume "Tit-for-Tat" (if you give me speed, I give you speed).
  * AI agent could learn which peers are "bursty" or "reliable" over time, predicting who will unchoke you faster than standard algorithms.
  * We will thus use Multi-Armed Bandit (Reinforcement Learning) algorithm for peer selection.

* #### **Masking IP / VPN:**
  * You cannot "mask" your IP in P2P without a relay. If you don't send your IP, the peer can't send you data.
  * SOCKS5 Proxy Support. We can add a feature to route all traffic through a proxy (like Tor or a commercial VPN proxy). This is how standard clients hide the user's IP.

* #### **ML for Legal/Illegal Detection:**
  * Challenge: You only see binary chunks, not the image/video content, until it's done.
  * NLP on Metadata.
  * Flag suspicious keywords or patterns often associated with malware or illegal content.

* #### **Avoid ISP Blocking**
  * ISPs block Torrenting by "Deep Packet Inspection" (DPI)—they see the handshake pattern.
  * _Solution:_ Message Stream Encryption (MSE/PE). 
  * Wraps the BitTorrent header in an encrypted stream (RC4) so it looks like random noise to the ISP, rather than a torrent.

## 🛠️ Technology Stack
* **Language:** Python 3.6+
* **Concurrency:** `asyncio` (Event Loop)
* **Networking:** `aiohttp` (Tracker HTTP), `asyncio` streams (TCP Peers)
* **Data:** `struct` (Binary packing), `hashlib` (SHA1 integrity)

## 📂 Architecture
The project is modularized to separate protocol logic from network management:
* `utils/bencoder.py`: Handles the raw data serialization.
* `core/tracker.py`: Manages the initial discovery of peers.
* `core/peer.py`: The state machine for individual peer connections (Handshake -> Choke/Unchoke -> Request).
* `network/download_manager.py`: The orchestrator that assigns work to peers.
