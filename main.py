import asyncio
import sys
import logging
import argparse

# Configure Logging
logging.basicConfig(
    filename='app.log',
    filemode='w',
    level=logging.DEBUG, 
    format='%(levelname)s:%(module)s:%(message)s'
)

from pytorrent.network.download_manager import DownloadManager

def main():
    parser = argparse.ArgumentParser(description="Asyncio BitTorrent Client")
    parser.add_argument('torrent_file', help="Path to the .torrent file")
    args = parser.parse_args()

    try:
        manager = DownloadManager(args.torrent_file)
        
        loop = asyncio.get_event_loop()
        loop.run_until_complete(manager.start())
        
    except KeyboardInterrupt:
        print("\nStopping download...")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()