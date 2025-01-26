"""
Application Configuration Module.

Manages application settings and environment variables using Pydantic for validation.
Provides centralized configuration management with type safety and validation.

Features:
- Environment variable loading and validation
- Secure credential management
- Configuration validation and type checking
- Path normalization for output directories
"""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from logger import LogManager


class Settings(BaseSettings):
    """
    Application configuration settings with validation.

    Manages and validates all application settings including:
    - Application identification
    - GitHub authentication
    - Repository configurations
    - Logging settings
    - Output directory configurations
    - OpenAI configuration
    - AI analysis settings

    Attributes:
        app_name (str): Name of the application
        dev (bool): Debug mode flag
        log_dir (str): Directory for log files
        github_token (SecretStr): GitHub API authentication token
        github_repo_urls (str): Comma-separated repository URLs
        log_level (int): Logging level (default: debug)
        report_output_dir (str): Directory for generated reports
        openai_api_key (SecretStr): OpenAI API key
        openai_llm_model (str): OpenAI LLM model to use
        ai_based (bool): Whether to use AI-based analysis
    """

    # Application settings
    app_name: str = Field(default="JsonFlow", description="Application name")
    dev: bool = Field(default=False, description="Debug mode")
    log_dir: str = Field(default="logs", description="Logging directory")

    # Optional configuration with defaults
    log_level: int = Field(default=10, description="Logging level, default debug")

    # Configure env file loading
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",  # Ignore extra fields in .env file
    )


# Create global settings instance
settings = Settings()

# Initialize logging configuration
logger = LogManager(
    app_name=settings.app_name.lower(),
    log_dir=settings.log_dir,
    development=settings.dev,
    level=settings.log_level,
).logger
