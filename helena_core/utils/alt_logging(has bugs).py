# helena_core/utils/logging.py
"""
Advanced logging system with encryption, rotation, and structured logging
"""
import logging
import logging.handlers
import json
import gzip
import threading
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional, List
from enum import Enum
import struct
import os

from cryptography.fernet import Fernet

class LogLevel(Enum):
    DEBUG = 10
    INFO = 20
    WARNING = 30
    ERROR = 40
    CRITICAL = 50
    SECURITY = 60  # Custom level for security events

class LogType(Enum):
    SYSTEM = "system"
    SECURITY = "security"
    PERFORMANCE = "performance"
    TRAINING = "training"
    MODULE = "module"
    USER = "user"
    AUDIT = "audit"

class StructuredLogRecord:
    """Structured log record with metadata"""
    
    def __init__(self, 
                 message: str,
                 log_type: LogType,
                 level: LogLevel,
                 source: str,
                 context: Optional[Dict[str, Any]] = None,
                 timestamp: Optional[datetime] = None):
        self.timestamp = timestamp or datetime.utcnow()
        self.message = message
        self.log_type = log_type
        self.level = level
        self.source = source
        self.context = context or {}
        self.thread_id = threading.get_ident()
        self.process_id = None  # Will be set during serialization
        
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            "timestamp": self.timestamp.isoformat(),
            "message": self.message,
            "type": self.log_type.value,
            "level": self.level.value,
            "level_name": self.level.name,
            "source": self.source,
            "context": self.context,
            "thread_id": self.thread_id,
            "process_id": self.process_id or 0
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'StructuredLogRecord':
        """Create from dictionary"""
        record = cls(
            message=data["message"],
            log_type=LogType(data["type"]),
            level=LogLevel(data["level"]),
            source=data["source"],
            context=data.get("context", {}),
            timestamp=datetime.fromisoformat(data["timestamp"])
        )
        record.thread_id = data.get("thread_id", 0)
        record.process_id = data.get("process_id", 0)
        return record

class EncryptedRotatingFileHandler(logging.handlers.RotatingFileHandler):
    """Log handler with encryption and rotation"""
    
    def __init__(self, 
                 filename: str,
                 encryption_key: Optional[bytes] = None,
                 max_bytes: int = 10 * 1024 * 1024,  # 10MB
                 backup_count: int = 5,
                 encoding: str = 'utf-8'):
        
        # Create directory if needed
        Path(filename).parent.mkdir(parents=True, exist_ok=True)
        
        super().__init__(filename, maxBytes=max_bytes, backupCount=backup_count, encoding=encoding)

         # Force binary mode immediately
        self.stream = self._open()
        
        self.encryption_key = encryption_key
        if encryption_key:
            import base64
            # Ensure the key is 32 bytes and encode it to URL-safe base64
            fernet_key = base64.urlsafe_b64encode(encryption_key)
            self.fernet = Fernet(fernet_key)
        else:
            self.fernet = None
        
        # Write header to identify encrypted logs
        if self.fernet:
            self._write_header()
    
    def _write_header(self):
        """Write encryption header to log file"""
        header = b'HELENA_ENCRYPTED_LOG_V1\n'
        self.stream.write(header)
        self.stream.flush()
    
    def emit(self, record: logging.LogRecord):
        """Emit a record with optional encryption"""
        try:
            msg = self.format(record)
            
            # Convert to structured format if it's a StructuredLogRecord
            if hasattr(record, 'structured_data'):
                log_data = record.structured_data.to_dict()
                serialized = json.dumps(log_data).encode('utf-8')
            else:
                # Fallback to simple format
                log_entry = {
                    "timestamp": datetime.utcnow().isoformat(),
                    "message": msg,
                    "level": record.levelno,
                    "level_name": record.levelname,
                    "source": record.name,
                    "context": getattr(record, 'context', {})
                }
                serialized = json.dumps(log_entry).encode('utf-8')
            
            # Encrypt if configured
            if self.fernet:
                encrypted = self.fernet.encrypt(serialized)
                # Add length prefix for easy reading
                length_prefix = struct.pack('>I', len(encrypted))
                data = length_prefix + encrypted + b'\n'
            else:
                data = serialized + b'\n'
            
            self.stream.write(data)
            self.flush()
            
        except Exception:
            self.handleError(record)
    
    def doRollover(self):
        """Perform log rotation with encryption"""
        if self.stream:
            self.stream.close()
            self.stream = None
        
        # Rotate files
        if self.backupCount > 0:
            for i in range(self.backupCount - 1, 0, -1):
                sfn = self.rotation_filename("%s.%d" % (self.baseFilename, i))
                dfn = self.rotation_filename("%s.%d" % (self.baseFilename, i + 1))
                if os.path.exists(sfn):
                    if os.path.exists(dfn):
                        os.remove(dfn)
                    os.rename(sfn, dfn)
            
            dfn = self.rotation_filename(self.baseFilename + ".1")
            if os.path.exists(dfn):
                os.remove(dfn)
            os.rename(self.baseFilename, dfn)
        
        # Compress old logs (except current)
        self._compress_old_logs()
        
        # Open new file and write header
        self.stream = self._open()
        if self.fernet:
            self._write_header()
    
    def _compress_old_logs(self):
        """Compress rotated log files"""
        for i in range(2, self.backupCount + 1):
            log_file = Path(f"{self.baseFilename}.{i}")
            if log_file.exists() and not log_file.with_suffix('.gz').exists():
                try:
                    with open(log_file, 'rb') as f_in:
                        with gzip.open(f"{log_file}.gz", 'wb') as f_out:
                            f_out.writelines(f_in)
                    log_file.unlink()  # Remove uncompressed file
                except Exception:
                    pass

class HelenaLogger:
    """Main logging interface for HELENA"""
    
    def __init__(self, 
                 log_directory: Path,
                 encryption_key: Optional[bytes] = None,
                 max_log_size_mb: int = 100,
                 log_retention_days: int = 30):
        
        self.log_directory = Path(log_directory)
        self.log_directory.mkdir(parents=True, exist_ok=True)
        
        self.encryption_key = encryption_key
        self.max_log_size = max_log_size_mb * 1024 * 1024
        self.retention_days = log_retention_days
        
        # Create separate loggers for different types
        self.loggers = {}
        self._setup_loggers()
        
        # Start cleanup thread
        self._start_cleanup_thread()
    
    def _setup_loggers(self):
        """Setup loggers for different log types"""
        
        # Base configuration
        log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        date_format = '%Y-%m-%d %H:%M:%S'
        
        # Create loggers for each type
        for log_type in LogType:
            logger_name = f"helena.{log_type.value}"
            logger = logging.getLogger(logger_name)
            logger.setLevel(logging.DEBUG)  # Capture all levels, filter by handler
            
            # Clear existing handlers
            logger.handlers.clear()
            
            # File handler for this log type
            log_file = self.log_directory / f"{log_type.value}.log"
            file_handler = EncryptedRotatingFileHandler(
                str(log_file),
                encryption_key=self.encryption_key,
                max_bytes=self.max_log_size,
                backup_count=10
            )
            file_handler.setLevel(logging.DEBUG)
            file_handler.setFormatter(logging.Formatter(log_format, datefmt=date_format))
            
            # Console handler for important messages
            console_handler = logging.StreamHandler()
            console_handler.setLevel(logging.WARNING)  # Only warnings and above to console
            console_handler.setFormatter(logging.Formatter(log_format, datefmt=date_format))
            
            logger.addHandler(file_handler)
            logger.addHandler(console_handler)
            
            self.loggers[log_type] = logger
    
    def log(self, 
            log_type: LogType,
            level: LogLevel,
            source: str,
            message: str,
            context: Optional[Dict[str, Any]] = None,
            structured: bool = True):
        """Log a message with structured data"""
        
        logger = self.loggers.get(log_type)
        if not logger:
            return
        
        if structured:
            # Create structured log record
            log_record = StructuredLogRecord(
                message=message,
                log_type=log_type,
                level=level,
                source=source,
                context=context
            )
            
            # Create logging record with extra data
            extra_data = {
                'structured_data': log_record,
                'context': context or {}
            }
            
            logger.log(level.value, message, extra=extra_data)
        else:
            # Simple logging
            logger.log(level.value, message)
    
    # Convenience methods
    def debug(self, source: str, message: str, context: Optional[Dict[str, Any]] = None):
        self.log(LogType.SYSTEM, LogLevel.DEBUG, source, message, context)
    
    def info(self, source: str, message: str, context: Optional[Dict[str, Any]] = None):
        self.log(LogType.SYSTEM, LogLevel.INFO, source, message, context)
    
    def warning(self, source: str, message: str, context: Optional[Dict[str, Any]] = None):
        self.log(LogType.SYSTEM, LogLevel.WARNING, source, message, context)
    
    def error(self, source: str, message: str, context: Optional[Dict[str, Any]] = None):
        self.log(LogType.SYSTEM, LogLevel.ERROR, source, message, context)
    
    def critical(self, source: str, message: str, context: Optional[Dict[str, Any]] = None):
        self.log(LogType.SYSTEM, LogLevel.CRITICAL, source, message, context)
    
    def security(self, source: str, message: str, context: Optional[Dict[str, Any]] = None):
        self.log(LogType.SECURITY, LogLevel.SECURITY, source, message, context)
    
    def audit(self, source: str, message: str, context: Optional[Dict[str, Any]] = None):
        self.log(LogType.AUDIT, LogLevel.INFO, source, message, context)
    
    def performance(self, source: str, message: str, context: Optional[Dict[str, Any]] = None):
        self.log(LogType.PERFORMANCE, LogLevel.INFO, source, message, context)
    
    def get_logger(self, log_type: LogType) -> logging.Logger:
        """Get logger for specific type"""
        return self.loggers.get(log_type)
    
    def export_logs(self, 
                    output_path: Path,
                    log_types: Optional[List[LogType]] = None,
                    start_time: Optional[datetime] = None,
                    end_time: Optional[datetime] = None) -> bool:
        """Export logs to file for analysis"""
        try:
            log_types = log_types or list(LogType)
            all_logs = []
            
            for log_type in log_types:
                log_file = self.log_directory / f"{log_type.value}.log"
                if log_file.exists():
                    logs = self._read_log_file(log_file)
                    # Filter by time if specified
                    if start_time or end_time:
                        logs = self._filter_logs_by_time(logs, start_time, end_time)
                    all_logs.extend(logs)
            
            # Sort by timestamp
            all_logs.sort(key=lambda x: x.timestamp)
            
            # Write to output file
            with open(output_path, 'w') as f:
                for log in all_logs:
                    f.write(json.dumps(log.to_dict()) + '\n')
            
            return True
            
        except Exception as e:
            self.error("HelenaLogger", f"Failed to export logs: {e}")
            return False
    
    def _read_log_file(self, log_file: Path) -> List[StructuredLogRecord]:
        """Read and parse log file"""
        logs = []
        
        try:
            with open(log_file, 'rb') as f:
                # Check if encrypted
                header = f.read(24)  # Header length
                is_encrypted = header.startswith(b'HELENA_ENCRYPTED_LOG_V1\n')
                
                if is_encrypted and self.fernet:
                    # Read encrypted logs
                    while True:
                        # Read length prefix
                        length_bytes = f.read(4)
                        if not length_bytes or len(length_bytes) < 4:
                            break
                        
                        length = struct.unpack('>I', length_bytes)[0]
                        encrypted_data = f.read(length)
                        
                        if not encrypted_data or len(encrypted_data) < length:
                            break
                        
                        # Decrypt
                        try:
                            decrypted = self.fernet.decrypt(encrypted_data)
                            log_dict = json.loads(decrypted.decode('utf-8'))
                            logs.append(StructuredLogRecord.from_dict(log_dict))
                        except Exception:
                            # Skip corrupted entries
                            continue
                        
                        # Skip newline
                        f.read(1)
                else:
                    # Read plain text logs
                    f.seek(0)
                    for line in f:
                        try:
                            log_dict = json.loads(line.decode('utf-8').strip())
                            logs.append(StructuredLogRecord.from_dict(log_dict))
                        except Exception:
                            # Skip non-JSON lines
                            continue
        
        except Exception:
            pass
        
        return logs
    
    def _filter_logs_by_time(self, 
                            logs: List[StructuredLogRecord],
                            start_time: Optional[datetime],
                            end_time: Optional[datetime]) -> List[StructuredLogRecord]:
        """Filter logs by timestamp range"""
        filtered = []
        
        for log in logs:
            if start_time and log.timestamp < start_time:
                continue
            if end_time and log.timestamp > end_time:
                continue
            filtered.append(log)
        
        return filtered
    
    def _start_cleanup_thread(self):
        """Start thread to clean up old logs"""
        def cleanup_loop():
            import time
            while True:
                try:
                    self._cleanup_old_logs()
                    time.sleep(3600)  # Run every hour
                except Exception:
                    time.sleep(300)  # Wait 5 minutes on error
        
        thread = threading.Thread(target=cleanup_loop, daemon=True, name="LogCleanup")
        thread.start()
    
    def _cleanup_old_logs(self):
        """Clean up logs older than retention period"""
        cutoff_time = datetime.utcnow().timestamp() - (self.retention_days * 24 * 3600)
        
        for log_file in self.log_directory.glob("*.log*"):
            if log_file.stat().st_mtime < cutoff_time:
                try:
                    log_file.unlink()
                except Exception:
                    pass

# Global logger instance
_helena_logger: Optional[HelenaLogger] = None

def get_logger() -> HelenaLogger:
    """Get global logger instance"""
    global _helena_logger
    if _helena_logger is None:
        raise RuntimeError("HelenaLogger not initialized. Call init_logging() first.")
    return _helena_logger

def init_logging(log_directory: Path,
                 encryption_key: Optional[bytes] = None,
                 max_log_size_mb: int = 100,
                 log_retention_days: int = 30) -> HelenaLogger:
    """Initialize global logging system"""
    global _helena_logger
    if _helena_logger is not None:
        return _helena_logger
    
    _helena_logger = HelenaLogger(
        log_directory=log_directory,
        encryption_key=encryption_key,
        max_log_size_mb=max_log_size_mb,
        log_retention_days=log_retention_days
    )
    
    return _helena_logger
