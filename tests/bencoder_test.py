from pytorrent.utils import bencoder

# Test Data: A dictionary {"foo": ["bar", 123]}
# Bencoded: d3:fool3:bari123eee
raw_data = b'd3:fool3:bari123eee'

# 1. Test Decode
decoded = bencoder.decode(raw_data)
print(f"Decoded: {decoded}") 
# Expected: {b'foo': [b'bar', 123]}

# 2. Test Encode (Reverse)
encoded = bencoder.encode(decoded)
print(f"Encoded: {encoded}")
# Expected: b'd3:fool3:bari123eee' (Matches raw_data)

assert raw_data == encoded
print("SUCCESS: Encoder/Decoder Logic is solid.")