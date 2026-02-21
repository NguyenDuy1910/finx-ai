import os
import json
import configparser
from pathlib import Path
from typing import Dict, Any, Optional
from dataclasses import dataclass, field
from dotenv import load_dotenv


@dataclass
class AWSConfig:
    """AWS Configuration"""
    access_key_id: str = ""
    secret_access_key: str = ""
    session_token: Optional[str] = None
    region: str = "ap-southeast-1"
    profile: str = "default"
    
    @property
    def is_valid(self) -> bool:
        """Check if AWS credentials are valid"""
        return bool(self.access_key_id and self.secret_access_key)


@dataclass
class MCPConfig:
    """MCP Server Configuration"""
    server_url: str = "http://localhost:8000/sse"
    athena_database: str = "non_prod_uat_silver_zone"
    athena_output_location: str = ""
    timeout: int = 30
    max_retries: int = 3


@dataclass
class AIModelConfig:
    """AI Model Configuration"""
    provider: str = ""  # google, openai, anthropic
    model_id: str = ""
    api_key: str = ""
    temperature: float = 0.7
    max_tokens: int = 2000
    
    @property
    def is_valid(self) -> bool:
        """Check if model config is valid"""
        return bool(self.api_key)


@dataclass
class Neo4jConfig:
    """Neo4j Graph Database Configuration"""
    uri: str = "bolt://localhost:7687"
    username: str = "neo4j"
    password: str = ""
    database: str = "neo4j"
    enabled: bool = True
    
    @property
    def is_valid(self) -> bool:
        """Check if Neo4j config is valid"""
        return bool(self.uri and self.username and self.password)


@dataclass
class FalkorDBConfig:
    """FalkorDB Graph Database Configuration"""
    host: str = "localhost"
    port: int = 6379
    username: Optional[str] = None
    password: Optional[str] = None
    enabled: bool = True
    
    @property
    def is_valid(self) -> bool:
        """Check if FalkorDB config is valid"""
        return bool(self.host and self.port)


@dataclass
class AppConfig:
    """Main Application Configuration"""
    aws: AWSConfig = field(default_factory=AWSConfig)
    mcp: MCPConfig = field(default_factory=MCPConfig)
    ai_model: AIModelConfig = field(default_factory=AIModelConfig)
    neo4j: Neo4jConfig = field(default_factory=Neo4jConfig)
    falkordb: FalkorDBConfig = field(default_factory=FalkorDBConfig)
    debug: bool = False
    log_level: str = "INFO"


class ConfigLoader:
    """Configuration loader with multiple sources"""
    
    def __init__(self, config_dir: Optional[Path] = None):
        """
        Initialize configuration loader.
        
        Args:
            config_dir: Directory containing config files (default: ./config)
        """
        if config_dir is None:
            # Get project root (finx-agentic directory)
            # config_loader.py is in finx-agentic/config/
            # So parent is config/, parent.parent is finx-agentic/
            self.config_dir = Path(__file__).parent
        else:
            self.config_dir = Path(config_dir)
        
        # Project root is finx-agentic directory
        self.project_root = Path(__file__).parent.parent
        self.env_file = self.project_root / ".env"
        self.config_file = self.config_dir / "config.json"
        
    def load(self) -> AppConfig:
        """
        Load configuration from all sources.
        Priority: .env > AWS credentials > config.json
        """
        config = AppConfig()
        
        # 1. Load from config.json (lowest priority)
        self._load_from_json(config)
        
        # 2. Load from AWS credentials file (medium priority)
        self._load_aws_credentials(config)
        
        # 3. Load from .env file (highest priority)
        self._load_from_env(config)
        
        # 4. Validate configuration
        self._validate_config(config)
        
        return config
    
    def _load_from_json(self, config: AppConfig) -> None:
        """Load configuration from config.json"""
        if not self.config_file.exists():
            print(f"Warning: Config file not found at {self.config_file}")
            return
        
        try:
            with open(self.config_file, 'r') as f:
                data = json.load(f)
            
            # MCP Configuration
            if 'mcp' in data:
                mcp_data = data['mcp']
                config.mcp.server_url = mcp_data.get('endpoint', config.mcp.server_url)
                config.mcp.timeout = mcp_data.get('timeout', config.mcp.timeout)
            
            # AI Model Configuration
            if 'prompts' in data:
                prompts_data = data['prompts']
                config.ai_model.temperature = prompts_data.get('temperature', config.ai_model.temperature)
                config.ai_model.max_tokens = prompts_data.get('max_tokens', config.ai_model.max_tokens)
            
            # Agents Configuration
            if 'agents' in data:
                agents_data = data['agents']
                config.mcp.timeout = agents_data.get('default_timeout', config.mcp.timeout)
                config.mcp.max_retries = agents_data.get('max_retries', config.mcp.max_retries)
            
        except Exception as e:
            print(f"Error loading config.json: {e}")
    
    def _load_aws_credentials(self, config: AppConfig) -> None:
        """Load AWS credentials from ~/.aws/credentials"""
        aws_dir = Path.home() / ".aws"
        credentials_file = aws_dir / "credentials"
        aws_config_file = aws_dir / "config"
        
        # Get profile from environment or use default
        profile = os.getenv("AWS_PROFILE", config.aws.profile)
        config.aws.profile = profile
        
        # Load credentials
        if credentials_file.exists():
            try:
                credentials = configparser.ConfigParser()
                credentials.read(credentials_file)
                
                if profile in credentials:
                    profile_data = credentials[profile]
                    config.aws.access_key_id = profile_data.get('aws_access_key_id', '')
                    config.aws.secret_access_key = profile_data.get('aws_secret_access_key', '')
                    config.aws.session_token = profile_data.get('aws_session_token')
            except Exception as e:
                print(f"Error loading AWS credentials: {e}")
        
        # Load AWS config (region, etc.)
        if aws_config_file.exists():
            try:
                aws_config = configparser.ConfigParser()
                aws_config.read(aws_config_file)
                
                section = f"profile {profile}" if profile != "default" else "default"
                if section in aws_config:
                    section_data = aws_config[section]
                    config.aws.region = section_data.get('region', config.aws.region)
            except Exception as e:
                print(f"Error loading AWS config: {e}")
    
    def _load_from_env(self, config: AppConfig) -> None:
        """Load configuration from .env file and environment variables"""
        # Load .env file if exists using python-dotenv
        if self.env_file.exists():
            load_dotenv(self.env_file, override=True)
            print(f"Loaded environment variables from {self.env_file}")
        
        # AWS Configuration (only override if not placeholder values)
        env_access_key = os.getenv('AWS_ACCESS_KEY_ID', '')
        env_secret_key = os.getenv('AWS_SECRET_ACCESS_KEY', '')
        
        # Only use env vars if they're not placeholder values
        if env_access_key and env_access_key != 'your_aws_access_key':
            config.aws.access_key_id = env_access_key
        if env_secret_key and env_secret_key != 'your_aws_secret_key':
            config.aws.secret_access_key = env_secret_key
            
        config.aws.session_token = os.getenv('AWS_SESSION_TOKEN', config.aws.session_token)
        config.aws.region = os.getenv('AWS_REGION', config.aws.region)
        config.aws.profile = os.getenv('AWS_PROFILE', config.aws.profile)
        
        # MCP Configuration
        config.mcp.server_url = os.getenv('MCP_SERVER_URL', config.mcp.server_url)
        config.mcp.athena_database = os.getenv('ATHENA_DATABASE', config.mcp.athena_database)
        config.mcp.athena_output_location = os.getenv(
            'ATHENA_OUTPUT_LOCATION', 
            config.mcp.athena_output_location
        )
        
        # AI Model Configuration
        config.ai_model.provider = os.getenv('AI_PROVIDER', config.ai_model.provider).lower()
        config.ai_model.model_id = os.getenv('AI_MODEL_ID', config.ai_model.model_id)
        
        # API Keys (based on provider)
        if config.ai_model.provider == 'google':
            config.ai_model.api_key = os.getenv('GOOGLE_API_KEY', '')
        elif config.ai_model.provider == 'openai':
            config.ai_model.api_key = os.getenv('OPENAI_API_KEY', '')
        elif config.ai_model.provider == 'anthropic':
            config.ai_model.api_key = os.getenv('ANTHROPIC_API_KEY', '')
        
        # Neo4j Configuration
        config.neo4j.uri = os.getenv('NEO4J_URI', config.neo4j.uri)
        config.neo4j.username = os.getenv('NEO4J_USERNAME', config.neo4j.username)
        config.neo4j.password = os.getenv('NEO4J_PASSWORD', config.neo4j.password)
        config.neo4j.database = os.getenv('NEO4J_DATABASE', config.neo4j.database)
        config.neo4j.enabled = os.getenv('NEO4J_ENABLED', 'true').lower() in ('true', '1', 'yes')

        # FalkorDB Configuration
        config.falkordb.host = os.getenv('FALKORDB_HOST', config.falkordb.host)
        config.falkordb.port = int(os.getenv('FALKORDB_PORT', str(config.falkordb.port)))
        config.falkordb.username = os.getenv('FALKORDB_USERNAME', config.falkordb.username)
        config.falkordb.password = os.getenv('FALKORDB_PASSWORD', config.falkordb.password)
        config.falkordb.enabled = os.getenv('FALKORDB_ENABLED', 'true').lower() in ('true', '1', 'yes')

        # General settings
        config.debug = os.getenv('DEBUG', 'false').lower() in ('true', '1', 'yes')
        config.log_level = os.getenv('LOG_LEVEL', config.log_level).upper()
    
    def _validate_config(self, config: AppConfig) -> None:
        """Validate configuration and print warnings"""
        warnings = []
        
        if not config.aws.is_valid:
            warnings.append("AWS credentials not found. Please set AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY or configure ~/.aws/credentials")
        
        if not config.ai_model.is_valid:
            warnings.append(f"AI API key not found. Please set {config.ai_model.provider.upper()}_API_KEY")
        
        if warnings:
            print("\n" + "=" * 60)
            print("Configuration Warnings:")
            for warning in warnings:
                print(f" {warning}")
            print("=" * 60 + "\n")
    

# Singleton instance
_config_loader = None
_app_config = None


def get_config_loader() -> ConfigLoader:
    """Get or create config loader singleton"""
    global _config_loader
    if _config_loader is None:
        _config_loader = ConfigLoader()
    return _config_loader


def get_config() -> AppConfig:
    """Get or load application configuration"""
    global _app_config
    if _app_config is None:
        loader = get_config_loader()
        _app_config = loader.load()
    return _app_config


def reload_config() -> AppConfig:
    """Reload configuration from all sources"""
    global _app_config
    loader = get_config_loader()
    _app_config = loader.load()
    return _app_config
