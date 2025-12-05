import hashlib
import random

# The 96-bit prime defined in the MSE specification
MSE_PRIME = 0xFFFFFFFFFFFFFFFFC90FDAA22168C234C4C6628B80DC1CD129024E088A67CC74020BBEA63B139B22514A08798E3404DDEF9519B3CD3A431B302B0A6DF25F14374FE1356D6D51C245E485B576625E7EC6F44C42E9A63A3620FFFFFFFFFFFFFFFF
MSE_GENERATOR = 2

class RC4:
    # Pure Python implementation of the RC4 stream cipher.
    def __init__(self, key):
        self.state = list(range(256))
        self.x = 0
        self.y = 0
        j = 0
        
        # Key Scheduling Algorithm (KSA)
        for i in range(256):
            j = (j + self.state[i] + key[i % len(key)]) % 256
            self.state[i], self.state[j] = self.state[j], self.state[i]
            
        # Discard first 1024 bytes (Standard practice in BitTorrent MSE)
        self.discard(1024)

    def discard(self, length):
        # Discard bytes to improve initial entropy
        for _ in range(length):
            self.x = (self.x + 1) % 256
            self.y = (self.y + self.state[self.x]) % 256
            self.state[self.x], self.state[self.y] = self.state[self.y], self.state[self.x]

    def crypt(self, data):
        # Encrypt/Decrypt data (XOR operation)
        out = []
        for char in data:
            self.x = (self.x + 1) % 256
            self.y = (self.y + self.state[self.x]) % 256
            self.state[self.x], self.state[self.y] = self.state[self.y], self.state[self.x]
            # XOR
            out.append(char ^ self.state[(self.state[self.x] + self.state[self.y]) % 256])
        return bytes(out)

class DiffieHellman:
    # Handles the Key Exchange math.
    def __init__(self):
        # Generate Private Key (random integer)
        self.private_key = random.getrandbits(160)
        # Generate Public Key: (G ^ Private) % P
        self.public_key = pow(MSE_GENERATOR, self.private_key, MSE_PRIME)
        self.shared_secret = None

    def compute_secret(self, remote_public_key_bytes):
        # Compute Secret = (Remote_Public ^ Private) % P
        # Convert bytes to int
        remote_public = int.from_bytes(remote_public_key_bytes, 'big')
        self.shared_secret = pow(remote_public, self.private_key, MSE_PRIME)
        return self.shared_secret_bytes()

    def shared_secret_bytes(self):
        # Convert int back to 96 bytes (768 bits)
        return self.shared_secret.to_bytes(96, 'big')

def get_encryption_keys(s_bytes, info_hash):
    # Generates the RC4 keys for incoming/outgoing streams using the shared secret.
    # KeyA = SHA1("keyA", S, S_hash)
    # KeyB = SHA1("keyB", S, S_hash)
    
    req1 = b"keyA"
    req2 = b"keyB"
    req3 = b"req1"
    
    s_hash = hashlib.sha1(s_bytes).digest()
    
    # Calculate RC4 keys (encryption and decryption)
    # Outgoing Key (We are Initiator 'A', so we use KeyA)
    enc_key = hashlib.sha1(req1 + s_bytes + s_hash).digest()
    
    # Incoming Key (Peer is 'B', so we use KeyB)
    dec_key = hashlib.sha1(req2 + s_bytes + s_hash).digest()
    
    return enc_key, dec_key