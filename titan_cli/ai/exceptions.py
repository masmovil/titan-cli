"""
Exceptions for AI system
"""


class AIError(Exception):
    """Base exception for AI errors"""
    pass


class AIConfigurationError(AIError):
    """AI configuration is invalid or missing"""
    pass


class AIProviderError(AIError):
    """Base exception for AI provider errors"""
    pass


class AIProviderAuthenticationError(AIProviderError):
    """Authentication failed (invalid API key)"""
    pass


class AIProviderRateLimitError(AIProviderError):
    """Rate limit exceeded"""
    pass


class AIProviderAPIError(AIProviderError):
    """API error from provider"""
    pass


class AIAnalysisError(AIError):
    """Base exception for AI analysis errors"""
    pass


class AIResponseParseError(AIAnalysisError):
    """Failed to parse AI response (e.g., invalid JSON)"""
    pass


class AINotAvailableError(AIError):
    """AI is not available or not configured"""
    pass
