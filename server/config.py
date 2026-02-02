import os
import json
from typing import Dict, Any, Optional
from dataclasses import dataclass, field
from pathlib import Path
import yaml
from dotenv import load_dotenv


# Load environment variables
load_dotenv()


@dataclass
class DatabaseConfig:
    """Database configuration"""
    host: str = "localhost"
    port: int = 5432
    name: str = "messaging_service"
    user: str = "postgres"
    password: str = ""
    pool_size: int = 10
    echo: bool = False


@dataclass
class RedisConfig:
    """Redis configuration"""
    host: str = "localhost"
    port: int = 6379
    db: int = 0
    password: str = ""
    ssl: bool = False
    connection_timeout: int = 30
    max_connections: int = 20


@dataclass
class SMTPConfig:
    """SMTP configuration for email sending"""
    server: str = "smtp.gmail.com"
    port: int = 587
    username: str = ""
    password: str = ""
    use_tls: bool = True
    from_email: str = ""
    timeout: int = 30


@dataclass
class LLMConfig:
    """LLM configuration"""
    api_key: str = ""
    model: str = "gpt-3.5-turbo"
    max_tokens: int = 200
    temperature: float = 0.7
    timeout: int = 60
    max_retries: int = 3


@dataclass
class AndroidConfig:
    """Android gateway configuration"""
    websocket_timeout: int = 30
    message_queue_timeout: int = 60
    max_connections: int = 10


@dataclass
class APIServerConfig:
    """API server configuration"""
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False
    log_level: str = "INFO"
    cors_origins: list = field(default_factory=lambda: ["*"])
    request_timeout: int = 30
    max_request_size: int = 1048576  # 1MB


@dataclass
class SecurityConfig:
    """Security configuration"""
    secret_key: str = ""
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    rate_limit_requests: int = 100
    rate_limit_window: int = 3600  # 1 hour


@dataclass
class AppConfig:
    """Main application configuration"""
    app_name: str = "LLM-Messaging-Service"
    version: str = "1.0.0"
    environment: str = "development"  # development, staging, production
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    redis: RedisConfig = field(default_factory=RedisConfig)
    smtp: SMTPConfig = field(default_factory=SMTPConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    android: AndroidConfig = field(default_factory=AndroidConfig)
    api_server: APIServerConfig = field(default_factory=APIServerConfig)
    security: SecurityConfig = field(default_factory=SecurityConfig)
    log_file: str = "logs/app.log"
    log_level: str = "INFO"
    contacts_db_path: str = "contacts.db"
    enable_metrics: bool = True
    enable_tracing: bool = False


class ConfigManager:
    """Configuration manager to handle application settings"""
    
    def __init__(self, config_file: Optional[str] = None):
        self.config_file = config_file
        self.config = self.load_config()
    
    def load_config(self) -> AppConfig:
        """Load configuration from file and environment variables"""
        config = AppConfig()
        
        # Load from file if provided
        if self.config_file and Path(self.config_file).exists():
            config = self._load_from_file(self.config_file, config)
        
        # Override with environment variables
        config = self._load_from_env(config)
        
        return config
    
    def _load_from_file(self, file_path: str, config: AppConfig) -> AppConfig:
        """Load configuration from YAML or JSON file"""
        file_path = Path(file_path)
        
        with open(file_path, 'r') as f:
            if file_path.suffix.lower() in ['.yaml', '.yml']:
                file_config = yaml.safe_load(f)
            elif file_path.suffix.lower() == '.json':
                file_config = json.load(f)
            else:
                raise ValueError(f"Unsupported config file format: {file_path.suffix}")
        
        if file_config:
            config = self._merge_config(config, file_config)
        
        return config
    
    def _load_from_env(self, config: AppConfig) -> AppConfig:
        """Load configuration from environment variables"""
        # Database config
        config.database.host = os.getenv('DB_HOST', config.database.host)
        config.database.port = int(os.getenv('DB_PORT', config.database.port))
        config.database.name = os.getenv('DB_NAME', config.database.name)
        config.database.user = os.getenv('DB_USER', config.database.user)
        config.database.password = os.getenv('DB_PASSWORD', config.database.password)
        config.database.pool_size = int(os.getenv('DB_POOL_SIZE', config.database.pool_size))
        config.database.echo = os.getenv('DB_ECHO', str(config.database.echo)).lower() == 'true'
        
        # Redis config
        config.redis.host = os.getenv('REDIS_HOST', config.redis.host)
        config.redis.port = int(os.getenv('REDIS_PORT', config.redis.port))
        config.redis.db = int(os.getenv('REDIS_DB', config.redis.db))
        config.redis.password = os.getenv('REDIS_PASSWORD', config.redis.password)
        config.redis.ssl = os.getenv('REDIS_SSL', str(config.redis.ssl)).lower() == 'true'
        config.redis.connection_timeout = int(os.getenv('REDIS_TIMEOUT', config.redis.connection_timeout))
        config.redis.max_connections = int(os.getenv('REDIS_MAX_CONNECTIONS', config.redis.max_connections))
        
        # SMTP config
        config.smtp.server = os.getenv('SMTP_SERVER', config.smtp.server)
        config.smtp.port = int(os.getenv('SMTP_PORT', config.smtp.port))
        config.smtp.username = os.getenv('SMTP_USERNAME', config.smtp.username)
        config.smtp.password = os.getenv('SMTP_PASSWORD', config.smtp.password)
        config.smtp.use_tls = os.getenv('SMTP_USE_TLS', str(config.smtp.use_tls)).lower() == 'true'
        config.smtp.from_email = os.getenv('SMTP_FROM_EMAIL', config.smtp.from_email)
        config.smtp.timeout = int(os.getenv('SMTP_TIMEOUT', config.smtp.timeout))
        
        # LLM config
        config.llm.api_key = os.getenv('LLM_API_KEY', config.llm.api_key)
        config.llm.model = os.getenv('LLM_MODEL', config.llm.model)
        config.llm.max_tokens = int(os.getenv('LLM_MAX_TOKENS', config.llm.max_tokens))
        config.llm.temperature = float(os.getenv('LLM_TEMPERATURE', config.llm.temperature))
        config.llm.timeout = int(os.getenv('LLM_TIMEOUT', config.llm.timeout))
        config.llm.max_retries = int(os.getenv('LLM_MAX_RETRIES', config.llm.max_retries))
        
        # Android config
        config.android.websocket_timeout = int(os.getenv('ANDROID_WS_TIMEOUT', config.android.websocket_timeout))
        config.android.message_queue_timeout = int(os.getenv('ANDROID_QUEUE_TIMEOUT', config.android.message_queue_timeout))
        config.android.max_connections = int(os.getenv('ANDROID_MAX_CONNECTIONS', config.android.max_connections))
        
        # API server config
        config.api_server.host = os.getenv('API_HOST', config.api_server.host)
        config.api_server.port = int(os.getenv('API_PORT', config.api_server.port))
        config.api_server.debug = os.getenv('API_DEBUG', str(config.api_server.debug)).lower() == 'true'
        config.api_server.log_level = os.getenv('API_LOG_LEVEL', config.api_server.log_level)
        config.api_server.request_timeout = int(os.getenv('API_REQUEST_TIMEOUT', config.api_server.request_timeout))
        config.api_server.max_request_size = int(os.getenv('API_MAX_REQUEST_SIZE', config.api_server.max_request_size))
        
        # Security config
        config.security.secret_key = os.getenv('SECRET_KEY', config.security.secret_key)
        config.security.jwt_algorithm = os.getenv('JWT_ALGORITHM', config.security.jwt_algorithm)
        config.security.access_token_expire_minutes = int(os.getenv('JWT_EXPIRE_MINUTES', config.security.access_token_expire_minutes))
        config.security.rate_limit_requests = int(os.getenv('RATE_LIMIT_REQUESTS', config.security.rate_limit_requests))
        config.security.rate_limit_window = int(os.getenv('RATE_LIMIT_WINDOW', config.security.rate_limit_window))
        
        # App config
        config.app_name = os.getenv('APP_NAME', config.app_name)
        config.version = os.getenv('APP_VERSION', config.version)
        config.environment = os.getenv('ENVIRONMENT', config.environment)
        config.log_file = os.getenv('LOG_FILE', config.log_file)
        config.log_level = os.getenv('LOG_LEVEL', config.log_level)
        config.contacts_db_path = os.getenv('CONTACTS_DB_PATH', config.contacts_db_path)
        config.enable_metrics = os.getenv('ENABLE_METRICS', str(config.enable_metrics)).lower() == 'true'
        config.enable_tracing = os.getenv('ENABLE_TRACING', str(config.enable_tracing)).lower() == 'true'
        
        return config
    
    def _merge_config(self, config: AppConfig, file_config: Dict[str, Any]) -> AppConfig:
        """Merge file configuration with default config"""
        if 'database' in file_config:
            for key, value in file_config['database'].items():
                if hasattr(config.database, key):
                    setattr(config.database, key, value)
        
        if 'redis' in file_config:
            for key, value in file_config['redis'].items():
                if hasattr(config.redis, key):
                    setattr(config.redis, key, value)
        
        if 'smtp' in file_config:
            for key, value in file_config['smtp'].items():
                if hasattr(config.smtp, key):
                    setattr(config.smtp, key, value)
        
        if 'llm' in file_config:
            for key, value in file_config['llm'].items():
                if hasattr(config.llm, key):
                    setattr(config.llm, key, value)
        
        if 'android' in file_config:
            for key, value in file_config['android'].items():
                if hasattr(config.android, key):
                    setattr(config.android, key, value)
        
        if 'api_server' in file_config:
            for key, value in file_config['api_server'].items():
                if hasattr(config.api_server, key):
                    setattr(config.api_server, key, value)
        
        if 'security' in file_config:
            for key, value in file_config['security'].items():
                if hasattr(config.security, key):
                    setattr(config.security, key, value)
        
        if 'app' in file_config:
            for key, value in file_config['app'].items():
                if hasattr(config, key):
                    setattr(config, key, value)
        
        return config
    
    def get_config(self) -> AppConfig:
        """Get the loaded configuration"""
        return self.config
    
    def validate_config(self) -> bool:
        """Validate the configuration"""
        errors = []
        
        # Validate required fields
        if not self.config.llm.api_key and self.config.llm.api_key == "":
            errors.append("LLM_API_KEY is required")
        
        if not self.config.smtp.from_email:
            errors.append("SMTP_FROM_EMAIL is required")
        
        if not self.config.security.secret_key and self.config.environment == 'production':
            errors.append("SECRET_KEY is required in production")
        
        if errors:
            raise ValueError(f"Configuration validation failed: {'; '.join(errors)}")
        
        return True
    
    def save_config(self, file_path: str):
        """Save current configuration to file"""
        config_dict = {
            'app': {
                'app_name': self.config.app_name,
                'version': self.config.version,
                'environment': self.config.environment,
                'log_file': self.config.log_file,
                'log_level': self.config.log_level,
                'contacts_db_path': self.config.contacts_db_path,
                'enable_metrics': self.config.enable_metrics,
                'enable_tracing': self.config.enable_tracing,
            },
            'database': {
                'host': self.config.database.host,
                'port': self.config.database.port,
                'name': self.config.database.name,
                'user': self.config.database.user,
                'pool_size': self.config.database.pool_size,
                'echo': self.config.database.echo,
            },
            'redis': {
                'host': self.config.redis.host,
                'port': self.config.redis.port,
                'db': self.config.redis.db,
                'ssl': self.config.redis.ssl,
                'connection_timeout': self.config.redis.connection_timeout,
                'max_connections': self.config.redis.max_connections,
            },
            'smtp': {
                'server': self.config.smtp.server,
                'port': self.config.smtp.port,
                'use_tls': self.config.smtp.use_tls,
                'from_email': self.config.smtp.from_email,
                'timeout': self.config.smtp.timeout,
            },
            'llm': {
                'model': self.config.llm.model,
                'max_tokens': self.config.llm.max_tokens,
                'temperature': self.config.llm.temperature,
                'timeout': self.config.llm.timeout,
                'max_retries': self.config.llm.max_retries,
            },
            'android': {
                'websocket_timeout': self.config.android.websocket_timeout,
                'message_queue_timeout': self.config.android.message_queue_timeout,
                'max_connections': self.config.android.max_connections,
            },
            'api_server': {
                'host': self.config.api_server.host,
                'port': self.config.api_server.port,
                'debug': self.config.api_server.debug,
                'log_level': self.config.api_server.log_level,
                'request_timeout': self.config.api_server.request_timeout,
                'max_request_size': self.config.api_server.max_request_size,
            },
            'security': {
                'jwt_algorithm': self.config.security.jwt_algorithm,
                'access_token_expire_minutes': self.config.security.access_token_expire_minutes,
                'rate_limit_requests': self.config.security.rate_limit_requests,
                'rate_limit_window': self.config.security.rate_limit_window,
            }
        }
        
        file_path = Path(file_path)
        if file_path.suffix.lower() in ['.yaml', '.yml']:
            with open(file_path, 'w') as f:
                yaml.dump(config_dict, f, default_flow_style=False)
        elif file_path.suffix.lower() == '.json':
            with open(file_path, 'w') as f:
                json.dump(config_dict, f, indent=2)
        else:
            raise ValueError(f"Unsupported config file format: {file_path.suffix}")


# Global configuration instance
config_manager = ConfigManager()


def get_config() -> AppConfig:
    """Get the global configuration instance"""
    return config_manager.get_config()


def init_config(config_file: Optional[str] = None):
    """Initialize the configuration manager"""
    global config_manager
    config_manager = ConfigManager(config_file)
    config_manager.validate_config()


# Example configuration file content
EXAMPLE_CONFIG_YAML = """
app:
  app_name: "LLM-Messaging-Service"
  version: "1.0.0"
  environment: "development"
  log_file: "logs/app.log"
  log_level: "INFO"
  contacts_db_path: "contacts.db"
  enable_metrics: true
  enable_tracing: false

database:
  host: "localhost"
  port: 5432
  name: "messaging_service"
  user: "postgres"
  pool_size: 10
  echo: false

redis:
  host: "localhost"
  port: 6379
  db: 0
  ssl: false
  connection_timeout: 30
  max_connections: 20

smtp:
  server: "smtp.gmail.com"
  port: 587
  use_tls: true
  from_email: "your-email@gmail.com"
  timeout: 30

llm:
  model: "gpt-3.5-turbo"
  max_tokens: 200
  temperature: 0.7
  timeout: 60
  max_retries: 3

android:
  websocket_timeout: 30
  message_queue_timeout: 60
  max_connections: 10

api_server:
  host: "0.0.0.0"
  port: 8000
  debug: false
  log_level: "INFO"
  request_timeout: 30
  max_request_size: 1048576

security:
  jwt_algorithm: "HS256"
  access_token_expire_minutes: 30
  rate_limit_requests: 100
  rate_limit_window: 3600
"""


if __name__ == "__main__":
    # Example usage
    config = get_config()
    print(f"App: {config.app_name} v{config.version}")
    print(f"Environment: {config.environment}")
    print(f"Database: {config.database.host}:{config.database.port}/{config.database.name}")
    print(f"Redis: {config.redis.host}:{config.redis.port}")
    print(f"SMTP: {config.smtp.server}:{config.smtp.port}")
    print(f"LLM Model: {config.llm.model}")