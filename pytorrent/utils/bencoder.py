import logging

# Set up logging for this module
logger = logging.getLogger(__name__)

def parse_int(data, i):
    i += 1  # Skip 'i'
    j = data.index(b'e', i)
    # Convert bytes to string, then to int
    val = int(data[i:j]) 
    return val, j + 1

def parse_string(data, i):
    j = data.index(b':', i)
    length = int(data[i:j])
    j += 1
    # Read the string data
    s = data[j:j + length]
    return s, j + length

def parse_list(data, i):
    i += 1  # Skip 'l'
    l = []
    while i < len(data) and data[i] != ord('e'):
        val, i = parse_any(data, i)
        l.append(val)
    return l, i + 1

def parse_dict(data, i):
    i += 1  # Skip 'd'
    d = {}
    while i < len(data) and data[i] != ord('e'):
        # Keys in Bencode must be strings (bytes)
        key, i = parse_string(data, i)
        val, i = parse_any(data, i)
        d[key] = val
    return d, i + 1

def parse_any(data, i):
    # Determine type based on current character
    if data[i] == ord('i'):
        return parse_int(data, i)
    elif data[i] == ord('l'):
        return parse_list(data, i)
    elif data[i] == ord('d'):
        return parse_dict(data, i)
    # Check if it's a digit (0-9) via ASCII values
    elif ord('0') <= data[i] <= ord('9'):
        return parse_string(data, i)
    else:
        # Show a snippet of data for debugging
        raise ValueError(f"Invalid bencoded data at index {i}: {data[i:i+10]}")

def decode(data):
    """
    Public interface to decode bytes into a Python object.
    """
    if not isinstance(data, bytes):
        raise TypeError("Argument 'data' must be bytes")
    
    # Start parsing from index 0
    val, _ = parse_any(data, 0)
    return val

# ENCODER (Required for generating the Info Hash)
def encode(data):
    """
    Encodes a Python object (int, str, bytes, list, dict) back into Bencode.
    """
    if isinstance(data, int):
        # Format: i<int>e
        return b'i' + str(data).encode() + b'e'
    
    elif isinstance(data, str):
        # Convert string to bytes first
        encoded = data.encode('utf-8')
        return str(len(encoded)).encode() + b':' + encoded
    
    elif isinstance(data, bytes):
        # Format: <len>:<bytes>
        return str(len(data)).encode() + b':' + data
    
    elif isinstance(data, list):
        # Format: l<contents>e
        encoded_contents = b''.join([encode(item) for item in data])
        return b'l' + encoded_contents + b'e'
    
    elif isinstance(data, dict):
        # Format: d<contents>e
        # CRITICAL: Keys must be sorted to ensure consistent hashing
        encoded_contents = b''
        sorted_keys = sorted(data.keys())
        
        for key in sorted_keys:
            encoded_contents += encode(key)
            encoded_contents += encode(data[key])
        
        return b'd' + encoded_contents + b'e'
        
    else:
        raise TypeError(f"Cannot bencode type: {type(data)}")