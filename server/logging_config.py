import logging
import logging.config
import os
from datetime import datetime
from typing import Dict, Any
import json
from pathlib import Path


def setup_logging(log_level: str = "INFO", log_file: str = None):
    """
    Set up comprehensive logging configuration
    """
    # Create logs directory if it doesn't exist
    logs_dir = Path("logs")
    logs_dir.mkdir(exist_ok=True)
    
    # Define log file paths
    if not log_file:
        log_file = logs_dir / f"messaging_service_{datetime.now().strftime('%Y%m%d')}.log"
    
    # Error log file
    error_log_file = logs_dir / f"messaging_service_errors_{datetime.now().strftime('%Y%m%d')}.log"
    
    # Logging configuration
    logging_config = {
        'version': 1,
        'disable_existing_loggers': False,
        'formatters': {
            'standard': {
                'format': '%(asctime)s [%(levelname)s] %(name)s: %(message)s'
            },
            'detailed': {
                'format': '%(asctime)s [%(levelname)s] %(name)s:%(lineno)d: %(message)s'
            },
            'json': {
                'format': '%(asctime)s %(name)s %(levelname)s %(message)s',
                'class': 'server.logging.json_formatter.JsonFormatter'
            }
        },
        'handlers': {
            'console': {
                'level': log_level,
                'formatter': 'standard',
                'class': 'logging.StreamHandler',
                'stream': 'ext://sys.stdout'
            },
            'file': {
                'level': log_level,
                'formatter': 'detailed',
                'class': 'logging.handlers.RotatingFileHandler',
                'filename': str(log_file),
                'maxBytes': 10485760,  # 10MB
                'backupCount': 5
            },
            'error_file': {
                'level': 'ERROR',
                'formatter': 'detailed',
                'class': 'logging.handlers.RotatingFileHandler',
                'filename': str(error_log_file),
                'maxBytes': 10485760,  # 10MB
                'backupCount': 5
            }
        },
        'loggers': {
            '': {  # Root logger
                'handlers': ['console', 'file', 'error_file'],
                'level': log_level,
                'propagate': False
            },
            'server': {
                'handlers': ['console', 'file', 'error_file'],
                'level': log_level,
                'propagate': False
            },
            'uvicorn': {
                'handlers': ['console', 'file'],
                'level': log_level,
                'propagate': False
            },
            'uvicorn.error': {
                'handlers': ['console', 'error_file'],
                'level': 'ERROR',
                'propagate': False
            }
        }
    }
    
    logging.config.dictConfig(logging_config)
    
    # Also set the root logger level
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level.upper()))
    
    # Log service startup
    logger = logging.getLogger(__name__)
    logger.info(f"Logging initialized with level {log_level}")
    logger.info(f"Log file: {log_file}")
    logger.info(f"Error log file: {error_log_file}")


class JsonFormatter(logging.Formatter):
    """
    Custom JSON formatter for structured logging
    """
    def format(self, record):
        log_entry = {
            'timestamp': datetime.utcfromtimestamp(record.created).isoformat(),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
            'module': record.module,
            'function': record.funcName,
            'line': record.lineno,
        }
        
        # Add exception info if present
        if record.exc_info:
            log_entry['exception'] = self.formatException(record.exc_info)
        
        # Add extra fields if present
        if hasattr(record, 'extra_fields'):
            log_entry.update(record.extra_fields)
        
        return json.dumps(log_entry)


def get_logger(name: str) -> logging.Logger:
    """
    Get a configured logger instance
    """
    return logging.getLogger(name)


def log_api_call(endpoint: str, method: str, duration: float, status_code: int, user_id: str = None):
    """
    Log API call with performance metrics
    """
    logger = get_logger('api_monitoring')
    logger.info(
        f"API_CALL endpoint={endpoint} method={method} duration={duration:.3f}s status={status_code}",
        extra={
            'endpoint': endpoint,
            'method': method,
            'duration': duration,
            'status_code': status_code,
            'user_id': user_id
        }
    )


def log_message_event(message_id: str, event_type: str, details: Dict[str, Any] = None):
    """
    Log message lifecycle events
    """
    logger = get_logger('message_tracking')
    details_str = f" details={json.dumps(details)}" if details else ""
    logger.info(
        f"MESSAGE_EVENT message_id={message_id} event={event_type}{details_str}",
        extra={
            'message_id': message_id,
            'event_type': event_type,
            'details': details or {}
        }
    )


def log_performance(metric_name: str, value: float, unit: str = "", tags: Dict[str, str] = None):
    """
    Log performance metrics
    """
    logger = get_logger('performance')
    tags_str = f" tags={json.dumps(tags)}" if tags else ""
    logger.info(
        f"PERFORMANCE metric={metric_name} value={value} unit={unit}{tags_str}",
        extra={
            'metric_name': metric_name,
            'value': value,
            'unit': unit,
            'tags': tags or {}
        }
    )


# Initialize logging when module is imported
if __name__ != '__main__':
    setup_logging()