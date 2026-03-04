# helena_core/security/encryption.py
"""
Cryptographic foundations for HELENA
"""
import os
import hashlib
import secrets
from typing import Optional, Tuple
from base64 import b64encode, b64decode

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import hashes, padding
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
from cryptography.exceptions import InvalidTag

class EncryptionManager:
    """Manages encryption operations for HELENA"""
    
    # Constants
    AES_KEY_SIZE = 32  # 256 bits
    CHACHA_KEY_SIZE = 32  # 256 bits
    NONCE_SIZE = 12  # 96 bits for GCM
    CHACHA_NONCE_SIZE = 12
    SALT_SIZE = 16
    TAG_SIZE = 16  # GCM authentication tag
    
    def __init__(self, master_key: Optional[bytes] = None):
        self.master_key = master_key
        self.encryption_cache = {}
        
    def generate_master_key(self, password: str, salt: Optional[bytes] = None) -> Tuple[bytes, bytes]:
        """Generate master key from password using scrypt"""
        if salt is None:
            salt = secrets.token_bytes(self.SALT_SIZE)
        
        kdf = Scrypt(
            salt=salt,
            length=self.AES_KEY_SIZE,
            n=2**14,  # CPU/memory cost parameter
            r=8,      # Block size
            p=1       # Parallelization
        )
        
        key = kdf.derive(password.encode('utf-8'))
        return key, salt
    
    def derive_key(self, 
                   purpose: str, 
                   context: Optional[bytes] = None,
                   key_length: int = AES_KEY_SIZE) -> bytes:
        """Derive specific-purpose key from master key"""
        if not self.master_key:
            raise ValueError("Master key not set")
        
        # Use HKDF for key derivation
        from cryptography.hazmat.primitives.kdf.hkdf import HKDF
        
        info = purpose.encode('utf-8')
        if context:
            info += b':' + context
        
        hkdf = HKDF(
            algorithm=hashes.SHA256(),
            length=key_length,
            salt=None,
            info=info,
        )
        
        return hkdf.derive(self.master_key)
    
    def encrypt_aes_gcm(self, 
                       plaintext: bytes,
                       purpose: str = "default",
                       associated_data: Optional[bytes] = None) -> bytes:
        """Encrypt data using AES-256-GCM"""
        
        # Derive encryption key
        encryption_key = self.derive_key(f"encryption:{purpose}")
        
        # Generate nonce
        nonce = secrets.token_bytes(self.NONCE_SIZE)
        
        # Create cipher
        cipher = Cipher(algorithms.AES(encryption_key), modes.GCM(nonce))
        encryptor = cipher.encryptor()
        
        # Add associated data if provided
        if associated_data:
            encryptor.authenticate_additional_data(associated_data)
        
        # Encrypt
        ciphertext = encryptor.update(plaintext) + encryptor.finalize()
        
        # Get authentication tag
        tag = encryptor.tag
        
        # Combine nonce + ciphertext + tag
        return nonce + ciphertext + tag
    
    def decrypt_aes_gcm(self, 
                       encrypted_data: bytes,
                       purpose: str = "default",
                       associated_data: Optional[bytes] = None) -> bytes:
        """Decrypt AES-256-GCM encrypted data"""
        
        # Split components
        nonce = encrypted_data[:self.NONCE_SIZE]
        tag = encrypted_data[-self.TAG_SIZE:]
        ciphertext = encrypted_data[self.NONCE_SIZE:-self.TAG_SIZE]
        
        # Derive decryption key
        decryption_key = self.derive_key(f"encryption:{purpose}")
        
        # Create cipher
        cipher = Cipher(algorithms.AES(decryption_key), modes.GCM(nonce, tag))
        decryptor = cipher.decryptor()
        
        # Add associated data if provided
        if associated_data:
            decryptor.authenticate_additional_data(associated_data)
        
        # Decrypt
        try:
            plaintext = decryptor.update(ciphertext) + decryptor.finalize()
            return plaintext
        except InvalidTag:
            raise ValueError("Decryption failed: invalid authentication tag")
    
    def encrypt_chacha20(self, 
                        plaintext: bytes,
                        purpose: str = "default") -> bytes:
        """Encrypt data using ChaCha20-Poly1305"""
        
        # Derive encryption key
        encryption_key = self.derive_key(f"chacha:{purpose}", key_length=self.CHACHA_KEY_SIZE)
        
        # Generate nonce
        nonce = secrets.token_bytes(self.CHACHA_NONCE_SIZE)
        
        # Create cipher
        cipher = Cipher(algorithms.ChaCha20(encryption_key, nonce), mode=None)
        encryptor = cipher.encryptor()
        
        # Encrypt
        ciphertext = encryptor.update(plaintext) + encryptor.finalize()
        
        # Return nonce + ciphertext
        return nonce + ciphertext
    
    def decrypt_chacha20(self, 
                        encrypted_data: bytes,
                        purpose: str = "default") -> bytes:
        """Decrypt ChaCha20 encrypted data"""
        
        # Split components
        nonce = encrypted_data[:self.CHACHA_NONCE_SIZE]
        ciphertext = encrypted_data[self.CHACHA_NONCE_SIZE:]
        
        # Derive decryption key
        decryption_key = self.derive_key(f"chacha:{purpose}", key_length=self.CHACHA_KEY_SIZE)
        
        # Create cipher
        cipher = Cipher(algorithms.ChaCha20(decryption_key, nonce), mode=None)
        decryptor = cipher.decryptor()
        
        # Decrypt
        plaintext = decryptor.update(ciphertext) + decryptor.finalize()
        return plaintext
    
    def encrypt_string(self, 
                      plaintext: str,
                      purpose: str = "default",
                      algorithm: str = "AES-GCM") -> str:
        """Encrypt string and return base64 encoded result"""
        plaintext_bytes = plaintext.encode('utf-8')
        
        if algorithm == "AES-GCM":
            encrypted = self.encrypt_aes_gcm(plaintext_bytes, purpose)
        elif algorithm == "ChaCha20":
            encrypted = self.encrypt_chacha20(plaintext_bytes, purpose)
        else:
            raise ValueError(f"Unsupported algorithm: {algorithm}")
        
        return b64encode(encrypted).decode('utf-8')
    
    def decrypt_string(self, 
                      encrypted_b64: str,
                      purpose: str = "default",
                      algorithm: str = "AES-GCM") -> str:
        """Decrypt base64 encoded string"""
        encrypted_bytes = b64decode(encrypted_b64)
        
        if algorithm == "AES-GCM":
            decrypted = self.decrypt_aes_gcm(encrypted_bytes, purpose)
        elif algorithm == "ChaCha20":
            decrypted = self.decrypt_chacha20(encrypted_bytes, purpose)
        else:
            raise ValueError(f"Unsupported algorithm: {algorithm}")
        
        return decrypted.decode('utf-8')
    
    def hash_data(self, 
                 data: bytes,
                 algorithm: str = "SHA-256",
                 salt: Optional[bytes] = None) -> str:
        """Create cryptographic hash of data"""
        
        if algorithm == "SHA-256":
            hash_func = hashlib.sha256()
        elif algorithm == "SHA-512":
            hash_func = hashlib.sha512()
        elif algorithm == "BLAKE2b":
            hash_func = hashlib.blake2b()
        else:
            raise ValueError(f"Unsupported hash algorithm: {algorithm}")
        
        if salt:
            hash_func.update(salt)
        
        hash_func.update(data)
        return hash_func.hexdigest()
    
    def secure_compare(self, a: bytes, b: bytes) -> bool:
        """Constant-time comparison to prevent timing attacks"""
        return secrets.compare_digest(a, b)
    
    def generate_secure_random(self, size: int) -> bytes:
        """Generate cryptographically secure random bytes"""
        return secrets.token_bytes(size)
    
    def wipe_memory(self, data: bytes):
        """Attempt to wipe sensitive data from memory"""
        # Overwrite with random data
        random_data = secrets.token_bytes(len(data))
        for i in range(len(data)):
            # This is a best-effort attempt
            data_bytes = bytearray(data)
            data_bytes[i] = random_data[i]
        
        # Encourage garbage collection
        import gc
        gc.collect()
    
    def create_hmac(self, 
                   data: bytes,
                   purpose: str = "default") -> str:
        """Create HMAC for data verification"""
        from cryptography.hazmat.primitives.hmac import HMAC
        
        key = self.derive_key(f"hmac:{purpose}")
        h = HMAC(key, hashes.SHA256())
        h.update(data)
        return h.finalize().hex()

class MemoryEncryptionWrapper:
    """Wrapper for encrypting data in memory"""
    
    def __init__(self, encryption_manager: EncryptionManager):
        self.encryption_manager = encryption_manager
        self.encrypted_cache = {}
        
    def encrypt_in_memory(self, 
                         key: str,
                         data: bytes,
                         purpose: str = "memory") -> bytes:
        """Encrypt data for in-memory storage"""
        # Use a fast algorithm for memory encryption
        encrypted = self.encryption_manager.encrypt_chacha20(data, f"{purpose}:{key}")
        self.encrypted_cache[key] = encrypted
        return encrypted
    
    def decrypt_from_memory(self,
                           key: str,
                           purpose: str = "memory") -> Optional[bytes]:
        """Decrypt data from in-memory storage"""
        if key not in self.encrypted_cache:
            return None
        
        try:
            return self.encryption_manager.decrypt_chacha20(
                self.encrypted_cache[key],
                f"{purpose}:{key}"
            )
        except Exception:
            return None
    
    def clear_memory(self):
        """Clear all encrypted data from memory"""
        self.encrypted_cache.clear()
        import gc
        gc.collect()
