import json

def encode_payload(success: bool, data: str | list) -> str:
    # Use JSON for secure IPC (avoid Pickling untrusted data)
    return json.dumps({'success': success, 'data': data})

def decode_payload(payload: str) -> dict:
    return json.loads(payload)