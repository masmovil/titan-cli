# AI Configuration Guide

Complete guide for configuring AI providers in Titan CLI, including support for corporate gateways and custom endpoints.

## Quick Start

```bash
# Interactive configuration
titan ai configure

# Test your configuration
titan ai test
```

## Supported Providers

- **Anthropic (Claude)** - Claude 3.5 Sonnet, Opus, Haiku
- **OpenAI (GPT)** - GPT-4, GPT-4 Turbo, GPT-3.5
- **Google (Gemini)** - Gemini 1.5 Pro, Flash

## Environment Variable Detection

Titan CLI automatically detects AI configuration from environment variables, making it ideal for corporate environments with centralized gateway management.

### Standard Configuration

For standard API usage:

```bash
# Anthropic
export ANTHROPIC_API_KEY="sk-ant-..."

# OpenAI
export OPENAI_API_KEY="sk-..."

# Gemini
export GEMINI_API_KEY="AIza..."
```

### Corporate Gateway Configuration

For custom endpoints (corporate gateways, proxies):

```bash
# MasOrange example
export ANTHROPIC_API_KEY="sk-bA3iTR0JPtyPZlMvmUI5NQ"
export ANTHROPIC_BASE_URL="https://llm.tools.cloud.masorange.es"
export ANTHROPIC_DEFAULT_SONNET_MODEL="claude-sonnet-4-5"

# Generic corporate gateway
export OPENAI_API_KEY="your-corporate-key"
export OPENAI_BASE_URL="https://ai.yourcompany.com"
export OPENAI_DEFAULT_MODEL="gpt-4-custom"
```

### Supported Environment Variables

#### Anthropic
- `ANTHROPIC_API_KEY` - API key
- `ANTHROPIC_BASE_URL` - Custom endpoint URL
- `ANTHROPIC_DEFAULT_MODEL` - Default model name
- `ANTHROPIC_DEFAULT_SONNET_MODEL` - Sonnet-specific default

#### OpenAI
- `OPENAI_API_KEY` - API key
- `OPENAI_BASE_URL` or `OPENAI_API_BASE` - Custom endpoint URL
- `OPENAI_DEFAULT_MODEL` or `OPENAI_MODEL` - Default model name

#### Gemini
- `GEMINI_API_KEY` or `GOOGLE_API_KEY` - API key
- `GEMINI_BASE_URL` - Custom endpoint URL
- `GEMINI_DEFAULT_MODEL` or `GEMINI_MODEL` - Default model name

## Interactive Configuration

When you run `titan ai configure`, Titan will:

1. **Detect Environment Variables**
   - Automatically detect configured providers
   - Show corporate gateway information if detected
   - Indicate which providers have environment configuration

2. **Select Provider**
   - Choose from Anthropic, OpenAI, or Gemini
   - See badges for pre-configured providers

3. **Authentication**
   - Use existing API key from environment (if available)
   - Or securely prompt for new API key

4. **Corporate Gateway** (if detected)
   - Automatically detect corporate gateway URL
   - Ask if you want to use it
   - Display gateway domain and suggested model

5. **Model Selection**
   - Use environment-suggested model (if available)
   - Or select from popular models
   - Free-form input for custom models

6. **Advanced Options** (optional)
   - Temperature (0.0 - 2.0)
   - Max tokens

7. **Test Connection**
   - Verify configuration works
   - See actual model name returned
   - Sample response

## Configuration File

Configuration is stored in `~/.titan/config.toml`:

```toml
[ai]
provider = "anthropic"
model = "claude-sonnet-4-5"
base_url = "https://llm.tools.cloud.masorange.es"
temperature = 0.7
max_tokens = 8192
```

API keys are stored securely in your system keyring (not in the config file).

## Example Workflows

### First-Time Setup (Standard API)

```bash
$ titan ai configure

Configure AI Provider

  Select AI Provider

  📁 Providers
  1. Anthropic (Claude)
     Model: claude-3-opus-20240229
  2. OpenAI (GPT-4)
     Model: gpt-4-turbo
  3. Google (Gemini)
     Model: gemini-1.5-pro

Select an option: 1

Enter your Anthropic API Key: sk-ant-...

Model Selection for Claude (Anthropic)

Popular models:
  • claude-3-5-sonnet-20241022 (Latest Sonnet)
  • claude-3-opus-20240229 (Most capable)
  • claude-3-haiku-20240307 (Fastest)

Enter model name [claude-3-5-sonnet-20241022]:

✅ Configuration saved!
Provider: Claude (Anthropic)
Model: claude-3-5-sonnet-20241022

Test the connection? [Y/n]: y

ℹ️ Testing anthropic connection with model 'claude-3-5-sonnet-20241022'...
✅ Connection successful!
Model: claude-3-5-sonnet-20241022
Response: Hello!
```

### Corporate Gateway Setup (Auto-Detected)

```bash
$ titan ai configure

Configure AI Provider

🔍 Detected AI configuration from environment variables:
  • Anthropic: Corporate gateway at llm.tools.cloud.masorange.es
    Default model: claude-sonnet-4-5

💡 Titan will use these settings automatically if you select these providers.

  Select AI Provider

  📁 Providers
  1. Anthropic (Claude)
     🏢 Corporate gateway configured
  2. OpenAI (GPT-4)
     Model: gpt-4-turbo
  3. Google (Gemini)
     Model: gemini-1.5-pro

Select an option: 1

ℹ️ API key for anthropic already configured

🏢 Corporate gateway detected: llm.tools.cloud.masorange.es
Use the corporate gateway at https://llm.tools.cloud.masorange.es? [Y/n]: y

💡 Environment suggests model: claude-sonnet-4-5
Use the suggested model 'claude-sonnet-4-5'? [Y/n]: y

✅ Using model: claude-sonnet-4-5

✅ Configuration saved!
Provider: Claude (Anthropic)
Model: claude-sonnet-4-5
Endpoint: https://llm.tools.cloud.masorange.es

Test the connection? [Y/n]: y

ℹ️ Testing anthropic connection with model 'claude-sonnet-4-5' (custom endpoint)...
✅ Connection successful!
Model: claude-sonnet-4-5-20250929
Response: Hello!
```

## Benefits of Environment Detection

1. **Zero Configuration** - Works out-of-the-box in corporate environments
2. **Correct Models** - Automatically suggests gateway-compatible models
3. **No Manual Entry** - Reduces errors from incorrect model names
4. **Team Consistency** - Everyone uses same gateway/models via shared env vars
5. **CI/CD Ready** - Same env vars work in pipelines

## Troubleshooting

### Wrong Model Name Error

If you see:
```
❌ Connection failed: Error code: 400 - Invalid model name
```

**Solution**: Use `titan ai configure` to detect the correct model from environment variables, or check with your IT team for the correct model name for your corporate gateway.

### Gateway Not Detected

If your corporate gateway isn't detected:

1. Verify environment variables are set:
   ```bash
   env | grep ANTHROPIC
   ```

2. Ensure variables match supported patterns (see list above)

3. Run configuration again:
   ```bash
   titan ai configure
   ```

### API Key Not Found

If you get "API key not found":

1. Check keyring:
   ```bash
   # On macOS
   security find-generic-password -s "anthropic_api_key"
   ```

2. Or set via environment:
   ```bash
   export ANTHROPIC_API_KEY="your-key"
   ```

3. Or use configuration command:
   ```bash
   titan ai configure
   ```

## Security Best Practices

1. **Never commit API keys** to version control
2. **Use environment variables** for team/CI environments
3. **Use keyring** for personal development
4. **Rotate keys** regularly
5. **Use corporate gateways** when available for centralized management

## Advanced: Multiple Configurations

You can maintain different configurations per project by using project-specific `.titan/config.toml` files. The project config overrides global config.

```bash
# Global config
~/.titan/config.toml

# Project-specific config (overrides global)
/path/to/project/.titan/config.toml
```

---

**Need Help?**
- Run `titan ai configure` for interactive setup
- Run `titan ai test` to verify your configuration
- Check [AGENTS.md](../AGENTS.md) for development details
