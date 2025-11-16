# CLAUDE.md - AI Assistant Guide for ten_ai_base

**Last Updated**: 2025-11-16
**Version**: 0.7.3
**Type**: TEN Framework System Package

---

## Table of Contents

1. [Project Overview](#project-overview)
2. [Architecture & Design Philosophy](#architecture--design-philosophy)
3. [Directory Structure](#directory-structure)
4. [Core Concepts](#core-concepts)
5. [Base Extension Classes](#base-extension-classes)
6. [Development Workflows](#development-workflows)
7. [Coding Conventions](#coding-conventions)
8. [Testing Guidelines](#testing-guidelines)
9. [Common Patterns](#common-patterns)
10. [Troubleshooting](#troubleshooting)

---

## Project Overview

### What is ten_ai_base?

`ten_ai_base` is the foundational framework package for the TEN (Transformative Engagement Network) AI Framework. It provides base classes, interfaces, and utilities for building modular AI components including:

- **LLM (Large Language Models)** - Chat completion, streaming, tool calling
- **TTS (Text-to-Speech)** - Audio synthesis with state management
- **ASR (Automatic Speech Recognition)** - Speech-to-text conversion
- **MLLM (Multimodal LLM)** - Audio + text interactions

### Key Characteristics

- **Async-First**: Built entirely on Python's asyncio
- **Modular**: Extension-based architecture for composable AI services
- **Type-Safe**: Uses Pydantic v2 and TypedDict for runtime validation
- **Production-Ready**: Includes metrics, error handling, and state management
- **Framework Integration**: Depends on `ten_runtime_python` v0.11+

### Package Information

```json
{
  "type": "system",
  "name": "ten_ai_base",
  "version": "0.7.3",
  "dependencies": ["ten_runtime_python >= 0.11"]
}
```

---

## Architecture & Design Philosophy

### Async-First Design

ALL operations in this framework are asynchronous. Every extension method uses `async/await`:

```python
async def on_init(self, ten_env: AsyncTenEnv) -> None
async def on_start(self, ten_env: AsyncTenEnv) -> None
async def on_cmd(self, ten_env: AsyncTenEnv, cmd: Cmd) -> None
async def on_data(self, ten_env: AsyncTenEnv, data: Data) -> None
async def on_stop(self, ten_env: AsyncTenEnv) -> None
async def on_deinit(self, ten_env: AsyncTenEnv) -> None
```

### Extension Pattern

All AI components inherit from TEN's `AsyncExtension`:

```
AsyncExtension (ten_runtime)
    ├── AsyncLLMBaseExtension
    ├── AsyncLLM2BaseExtension
    ├── AsyncTTSBaseExtension
    ├── AsyncTTS2BaseExtension
    ├── AsyncASRBaseExtension
    ├── AsyncMLLMBaseExtension
    └── AsyncLLMToolBaseExtension
```

### Message-Driven Communication

Extensions communicate via **Commands** and **Data**:

- **Commands** (`Cmd`): Request/response RPC-style calls
- **Data** (`Data`): Streaming or fire-and-forget messages
- **Audio Frames** (`AudioFrame`): PCM audio data

---

## Directory Structure

```
ten_ai_base/
├── interface/ten_ai_base/          # Core implementation (21 modules)
│   ├── llm.py                      # LLM base (queue-based, v1)
│   ├── llm2.py                     # LLM base (concurrent, streaming, v2)
│   ├── llm_tool.py                 # Tool/function execution
│   ├── tts.py                      # TTS base (v1)
│   ├── tts2.py                     # TTS base (state machine, v2)
│   ├── tts2_http.py                # TTS HTTP client
│   ├── asr.py                      # ASR base
│   ├── mllm.py                     # Multimodal LLM base
│   ├── types.py                    # TypedDict definitions
│   ├── struct.py                   # Pydantic models
│   ├── message.py                  # Metrics/error message types
│   ├── config.py                   # BaseConfig for configuration
│   ├── helper.py                   # AsyncQueue, AsyncEventEmitter
│   ├── chat_memory.py              # Chat history management
│   ├── const.py                    # Constants (cmd/data names)
│   ├── transcription.py            # Transcription models
│   ├── timeline.py                 # Audio timeline tracking
│   ├── usage.py                    # Token usage tracking
│   ├── dumper.py                   # Debug utilities
│   └── utils.py                    # General utilities
│
├── tests/                          # Unit tests
│   ├── conftest.py                 # FakeApp fixture
│   ├── test_chat_memory.py
│   └── test_time_helper.py
│
├── integration_tests/              # Integration test suites
│   ├── test_async_llm_base/
│   ├── test_async_llm_tool_base/
│   ├── test_async_tts_base/
│   ├── test_async_tts2_base/
│   ├── test_config_python/
│   └── test_config_python_async/
│
├── api/                            # API definitions (currently empty)
├── manifest.json                   # TEN package manifest
├── requirements.txt                # Python dependencies
├── Taskfile.yml                    # Task automation
└── README.md
```

### Key Files to Know

| File | Purpose |
|------|---------|
| `interface/ten_ai_base/__init__.py` | Public API exports - check here for available imports |
| `interface/ten_ai_base/types.py` | Type definitions for LLM messages, tools, etc. |
| `interface/ten_ai_base/struct.py` | Pydantic request/response models |
| `interface/ten_ai_base/config.py` | Base configuration pattern |
| `Taskfile.yml` | Development tasks (install, lint, test) |

---

## Core Concepts

### 1. Configuration Management (BaseConfig)

**Pattern**: Use `BaseConfig` for all extension configurations

```python
from dataclasses import dataclass
from ten_ai_base import BaseConfig

@dataclass
class MyExtensionConfig(BaseConfig):
    api_key: str = ""
    model: str = "gpt-4"
    temperature: float = 0.7
    max_tokens: int = 2048

# Usage in extension
class MyExtension(AsyncLLMBaseExtension):
    async def on_start(self, ten_env: AsyncTenEnv):
        await super().on_start(ten_env)
        self.config = await MyExtensionConfig.create_async(ten_env)
```

**How it works**:
- Introspects dataclass fields
- Automatically loads properties from TEN environment
- Type-aware: `str`, `int`, `bool`, `float`, `dict` (JSON)
- Error handling built-in

### 2. Queue-Based Processing

Most base classes use `AsyncQueue` for sequential message processing:

```python
from ten_ai_base.helper import AsyncQueue

self.queue = AsyncQueue()

# Producer
await self.queue.put(item)
await self.queue.put(urgent_item, prepend=True)  # Jump queue

# Consumer
async def process_queue(self):
    while True:
        item = await self.queue.get()
        if item is None:
            break
        await self.handle_item(item)

# Cleanup
await self.queue.flush()  # Clear all items
```

### 3. Chat Memory

For maintaining conversation context:

```python
from ten_ai_base import AsyncChatMemory

self.memory = AsyncChatMemory(max_history_length=20)

# Add messages
await self.memory.put({"role": "user", "content": "Hello"})
await self.memory.put({"role": "assistant", "content": "Hi!"})

# Get history
messages = self.memory.get()

# Listen to events
async def on_expired(message):
    print(f"Message expired: {message}")

self.memory.on(AsyncChatMemory.EVENT_MEMORY_EXPIRED, on_expired)
```

**Auto-cleanup**:
- Removes oldest messages when exceeding `max_history_length`
- Prevents starting with assistant/tool messages
- Emits events on append/expire

### 4. Error Handling

Use structured errors with vendor information:

```python
from ten_ai_base.message import ModuleError, ModuleErrorCode, ModuleErrorVendorInfo

error = ModuleError(
    module="llm",
    code=ModuleErrorCode.FATAL_ERROR,
    message="API request failed",
    vendor_info=ModuleErrorVendorInfo(
        vendor="openai",
        code="429",
        message="Rate limit exceeded"
    )
)

# Send error to framework
error_msg = ErrorMessage.create(error)
await ten_env.send_data(Data.create("error"))
```

### 5. Metrics Tracking

Report performance metrics:

```python
from ten_ai_base.message import ModuleMetrics

metrics = ModuleMetrics(
    module="tts",
    vendor="google",
    metrics={
        "ttfb": 150,  # Time to first byte (ms)
        "ttft": 200,  # Time to first token
        "total_duration": 2500,
        "characters": 120
    },
    metadata={"request_id": "req-123"}
)

# Send to framework
metrics_msg = MetricsMessage.create(metrics)
await ten_env.send_data(Data.create("metrics"))
```

**Standard Metric Keys** (from `ModuleMetricKey`):
- `TTFW` - Time to First Word
- `TTFB` - Time to First Byte
- `TTFT` - Time to First Token
- `TTFS` - Time to First Sentence
- `TTLW` - Time to Last Word

---

## Base Extension Classes

### AsyncLLMBaseExtension (llm.py)

**Use for**: Queue-based LLM with tool support

**Key Abstract Methods**:
```python
async def on_call_chat_completion(
    self,
    ten_env: AsyncTenEnv,
    **kargs: LLMCallCompletionArgs
) -> None:
    # Handle command-based chat completion
    # Send response via ten_env.send_json()

async def on_data_chat_completion(
    self,
    ten_env: AsyncTenEnv,
    **kargs: LLMDataCompletionArgs
) -> None:
    # Handle data-based streaming completion
    # Stream via self.send_text_output()

async def on_tools_update(
    self,
    ten_env: AsyncTenEnv,
    tool: LLMToolMetadata
) -> None:
    # Register tools/functions
```

**Lifecycle**:
1. `on_start()` - Starts queue processor task
2. `on_cmd("chat_completion_call")` - Queues request
3. Queue processor calls `on_data_chat_completion()`
4. Results sent via `send_text_output()`

**Methods Available**:
- `queue_input_item(**kwargs)` - Add to processing queue
- `flush_input_items(ten_env)` - Cancel current + clear queue
- `send_text_output(env, text, end_of_segment)` - Stream text

### AsyncLLM2BaseExtension (llm2.py)

**Use for**: Modern streaming LLM with concurrent requests

**Key Abstract Methods**:
```python
async def on_chat_completion(
    self,
    ten_env: AsyncTenEnv,
    request: LLMRequest
) -> AsyncGenerator[str, None]:
    # Yield chunks of response
    # Supports streaming
    yield "Hello"
    yield " world"

async def on_abort_chat_completion(
    self,
    ten_env: AsyncTenEnv,
    request_id: str
) -> None:
    # Cancel in-flight request

async def on_retrieve_prompt(
    self,
    ten_env: AsyncTenEnv,
    request: LLMRequestRetrievePrompt
) -> LLMResponse:
    # Return cached context/prompt
```

**Differences from v1**:
- ✅ Concurrent request handling (not sequential)
- ✅ Streaming via async generators
- ✅ Request abort capability
- ✅ Request ID tracking
- ✅ In-flight request management

### AsyncTTSBaseExtension (tts.py)

**Use for**: Basic text-to-speech

**Key Abstract Methods**:
```python
async def on_request_tts(
    self,
    ten_env: AsyncTenEnv,
    input_text: str,
    **kargs
) -> None:
    # Convert text to audio
    # Send via self.send_audio_out()

async def on_cancel_tts(
    self,
    ten_env: AsyncTenEnv
) -> None:
    # Cancel current synthesis
```

**Methods Available**:
- `send_audio_out(env, audio_data, **options)` - Send PCM frames
- `send_transcript_out(env, transcription)` - Send text result

**PCM Options**:
```python
await self.send_audio_out(
    ten_env,
    audio_bytes,
    sample_rate=16000,
    bytes_per_sample=2,
    number_of_channels=1
)
```

### AsyncTTS2BaseExtension (tts2.py)

**Use for**: Advanced TTS with state machine and streaming input

**Key Abstract Methods**:
```python
async def on_request_tts2(
    self,
    ten_env: AsyncTenEnv,
    request_id: str,
    text: str,
    text_input_end: bool
) -> None:
    # Process text chunk
    # Can be called multiple times per request
    # text_input_end=True on final chunk

async def on_cancel_tts2(
    self,
    ten_env: AsyncTenEnv
) -> None:
    # Cancel all requests
```

**State Machine**:
```
QUEUED → PROCESSING → FINALIZING → COMPLETED
```

**Features**:
- ✅ Multipart text input (streaming text → streaming audio)
- ✅ Request-level state tracking
- ✅ Automatic metrics collection
- ✅ Flush handling

### AsyncASRBaseExtension (asr.py)

**Use for**: Automatic speech recognition

**Key Abstract Methods**:
```python
async def start_connection(self) -> None:
    # Initialize ASR connection

async def is_connected(self) -> bool:
    # Check connection status

async def send_audio_result(
    self,
    ten_env: AsyncTenEnv,
    result: ASRResult
) -> None:
    # Send transcription result

async def send_error(
    self,
    ten_env: AsyncTenEnv,
    error: ModuleError
) -> None:
    # Send error
```

**Features**:
- Audio frame buffering
- Timeline tracking
- TTFW/TTLW metrics
- Connection state management

### AsyncMLLMBaseExtension (mllm.py)

**Use for**: Multimodal LLM (audio + text)

**Features**:
- Audio frame processing
- Function calling
- Message context management
- Session management

---

## Development Workflows

### Initial Setup

```bash
# Install dependencies
task install

# This runs:
# - tman install --standalone  (TEN packages)
# - pip install -r requirements.txt
# - pip install -r tests/requirements.txt
```

### Development Tasks (Taskfile.yml)

```bash
# Clean build artifacts
task clean

# Lint code
task lint
task lint -- ./interface/ten_ai_base/llm.py  # Lint specific file

# Run all tests
task test

# Run unit tests only
task test-standalone

# Run integration tests only
task test-integration

# Run single extension test
task test-extension EXTENSION=integration_tests/test_async_llm_base
```

### Creating a New Extension

1. **Create extension class**:
```python
# my_extension.py
from ten_ai_base import AsyncLLMBaseExtension, BaseConfig
from dataclasses import dataclass

@dataclass
class MyConfig(BaseConfig):
    api_key: str = ""

class MyExtension(AsyncLLMBaseExtension):
    async def on_start(self, ten_env):
        await super().on_start(ten_env)
        self.config = await MyConfig.create_async(ten_env)

    async def on_call_chat_completion(self, ten_env, **kwargs):
        messages = kwargs.get("messages", [])
        # Call your LLM API
        response = await self.call_api(messages)
        await ten_env.send_json({"response": response})

    async def on_data_chat_completion(self, ten_env, **kwargs):
        # Stream responses
        async for chunk in self.stream_api():
            self.send_text_output(ten_env, chunk, False)
        self.send_text_output(ten_env, "", True)  # End
```

2. **Create addon registration**:
```python
# addon.py
from ten import Addon, register_addon_as_extension
from .extension import MyExtension

@register_addon_as_extension("my_extension")
class MyExtensionAddon(Addon):
    def on_create_instance(self, ten_env, name, context):
        return MyExtension(name)
```

3. **Create manifest.json**:
```json
{
  "type": "extension",
  "name": "my_extension",
  "version": "0.1.0",
  "dependencies": [
    {"type": "system", "name": "ten_ai_base", "version": "0.7"}
  ]
}
```

### Git Workflow

```bash
# Development happens on feature branches
git checkout -b feature/my-feature

# Make changes
git add .
git commit -m "feat: add new feature"

# Push to remote
git push -u origin feature/my-feature

# Create PR via GitHub UI
```

### CI/CD Pipeline

The GitHub Actions workflow (`.github/workflows/ci.yml`) automatically:

1. Installs dependencies
2. Runs linter (`task lint --errors-only`)
3. Runs all tests (`task test -s -v`)
4. On release tags: Updates version in manifest.json and publishes

**Container**: `ghcr.io/ten-framework/ten_agent_build:0.6.6`

---

## Coding Conventions

### Python Style

1. **Type Hints**: Always use type hints
```python
async def process_message(self, message: str) -> dict:
    return {"status": "ok"}
```

2. **Dataclasses for Config**:
```python
from dataclasses import dataclass

@dataclass
class Config(BaseConfig):
    field: str = "default"
```

3. **Pydantic for Validation**:
```python
from pydantic import BaseModel

class Request(BaseModel):
    request_id: str
    text: str
```

4. **TypedDict for Dictionaries**:
```python
from typing_extensions import TypedDict

class MessageParam(TypedDict):
    role: str
    content: str
```

### Async Patterns

1. **Always await async calls**:
```python
# ✅ Correct
await self.process()

# ❌ Wrong
self.process()  # Creates unawaited coroutine
```

2. **Use async context managers**:
```python
async with self._lock:
    self.shared_state.update()
```

3. **Proper task management**:
```python
# Create task
self.task = asyncio.create_task(self.long_running())

# Cancel on cleanup
if self.task:
    self.task.cancel()
    try:
        await self.task
    except asyncio.CancelledError:
        pass
```

### Error Handling

1. **Try-except in lifecycle methods**:
```python
async def on_start(self, ten_env):
    try:
        await super().on_start(ten_env)
        self.config = await MyConfig.create_async(ten_env)
    except Exception as e:
        await ten_env.log_error(f"Failed to start: {e}")
```

2. **Send structured errors**:
```python
error = ModuleError(
    module="llm",
    code=ModuleErrorCode.FATAL_ERROR,
    message=str(e)
)
await self.send_error(ten_env, error)
```

### Naming Conventions

- **Classes**: `PascalCase` (e.g., `AsyncLLMBaseExtension`)
- **Functions/Methods**: `snake_case` (e.g., `on_chat_completion`)
- **Constants**: `UPPER_SNAKE_CASE` (e.g., `CMD_CHAT_COMPLETION`)
- **Private members**: `_leading_underscore` (e.g., `_process_queue`)
- **Extension methods**: Prefix with `on_` (e.g., `on_cmd`, `on_data`)

### Logging

```python
# Use ten_env logging
await ten_env.log_debug("Debug message")
await ten_env.log_info("Info message")
await ten_env.log_warn("Warning message")
await ten_env.log_error("Error message")
await ten_env.log_category("custom", "message")
```

---

## Testing Guidelines

### Unit Test Structure

```python
# tests/test_my_feature.py
import pytest
from ten_ai_base import AsyncChatMemory

@pytest.mark.asyncio
async def test_chat_memory_basic():
    memory = AsyncChatMemory(max_history_length=5)
    await memory.put({"role": "user", "content": "Hello"})

    history = memory.get()
    assert len(history) == 1
    assert history[0]["role"] == "user"
```

### Integration Test Structure

Each integration test directory contains:

```
test_async_llm_base/
├── addon.py              # Addon registration
├── extension.py          # Test extension implementation
├── manifest.json         # Extension manifest
└── tests/
    ├── conftest.py       # Test fixtures
    ├── test_extension.py # Actual tests
    └── bin/start         # Test runner
```

**Example test_extension.py**:
```python
import pytest
from ten import AsyncTenEnv

@pytest.mark.asyncio
async def test_llm_completion():
    # Test implementation
    pass
```

### Running Tests

```bash
# All tests
task test

# Unit tests only
task test-standalone

# Specific integration test
task test-extension EXTENSION=integration_tests/test_async_llm_base

# With verbose output
task test -- -v -s
```

### Test Best Practices

1. **Use async fixtures**:
```python
@pytest.fixture
async def chat_memory():
    memory = AsyncChatMemory()
    yield memory
    # Cleanup if needed
```

2. **Mock external calls**:
```python
from unittest.mock import AsyncMock

async def test_api_call(mocker):
    mock_api = AsyncMock(return_value={"result": "ok"})
    mocker.patch("my_extension.api_call", mock_api)
```

3. **Test error cases**:
```python
@pytest.mark.asyncio
async def test_error_handling():
    with pytest.raises(ValueError):
        await process_invalid_input()
```

---

## Common Patterns

### Pattern 1: Streaming Text Output (LLM)

```python
class MyLLM(AsyncLLMBaseExtension):
    async def on_data_chat_completion(self, ten_env, **kwargs):
        messages = kwargs.get("messages", [])

        async for chunk in self.stream_from_api(messages):
            # Stream chunks
            self.send_text_output(ten_env, chunk, end_of_segment=False)

        # Signal completion
        self.send_text_output(ten_env, "", end_of_segment=True)
```

### Pattern 2: Streaming Audio Output (TTS)

```python
class MyTTS(AsyncTTSBaseExtension):
    async def on_request_tts(self, ten_env, input_text, **kwargs):
        async for audio_chunk in self.synthesize(input_text):
            await self.send_audio_out(
                ten_env,
                audio_chunk,
                sample_rate=24000,
                bytes_per_sample=2,
                number_of_channels=1
            )
```

### Pattern 3: State Machine (TTS2)

```python
class MyTTS2(AsyncTTS2BaseExtension):
    async def on_request_tts2(self, ten_env, request_id, text, text_input_end):
        # Update state
        self._update_request_state(request_id, RequestState.PROCESSING)

        # Process chunk
        await self.process_text_chunk(request_id, text)

        if text_input_end:
            # Finalize
            self._update_request_state(request_id, RequestState.FINALIZING)
            await self.finalize_request(request_id)
            self._update_request_state(request_id, RequestState.COMPLETED)
```

### Pattern 4: Tool Registration (LLM)

```python
class MyLLM(AsyncLLMBaseExtension):
    async def on_tools_update(self, ten_env, tool: LLMToolMetadata):
        self.tools[tool["name"]] = tool
        await ten_env.log_info(f"Registered tool: {tool['name']}")
```

### Pattern 5: Event Emission

```python
from ten_ai_base.helper import AsyncEventEmitter

class MyExtension(AsyncLLMBaseExtension):
    def __init__(self):
        super().__init__()
        self.events = AsyncEventEmitter()

    async def on_message_received(self, message):
        await self.events.emit("message", message)

    # Register listener
    async def setup_listeners(self):
        async def on_message(msg):
            await self.process(msg)

        self.events.on("message", on_message)
```

### Pattern 6: PCM Audio Writing

```python
from ten_ai_base.helper import PCMWriter

async def save_audio(self, audio_chunks):
    async with PCMWriter("output.pcm") as writer:
        for chunk in audio_chunks:
            await writer.write(chunk)
    # Auto-flushes on exit
```

### Pattern 7: Timeline Tracking (ASR)

```python
from ten_ai_base.timeline import Timeline

self.timeline = Timeline(
    start_time=time.time(),
    sample_rate=16000
)

# Add audio
frames_added = self.timeline.add_audio(audio_bytes)

# Get current position
duration_ms = self.timeline.get_duration_ms()
```

### Pattern 8: Usage Tracking (LLM)

```python
from ten_ai_base.usage import LLMUsage

usage = LLMUsage()
usage.set_completion_tokens(150)
usage.set_prompt_tokens(50)
usage.set_total_tokens(200)

total = usage.get_total_tokens()  # 200
```

---

## Troubleshooting

### Common Issues

#### 1. Extension Not Starting

**Symptom**: Extension doesn't initialize

**Solutions**:
- Check `on_init()` calls `await super().on_init(ten_env)`
- Verify manifest.json dependencies are correct
- Check TEN runtime logs for errors
- Ensure async methods use `await`

#### 2. Configuration Not Loading

**Symptom**: Config fields are empty/default

**Solutions**:
- Use `await MyConfig.create_async(ten_env)` (async version)
- Check property names match dataclass fields exactly
- Verify TEN environment has properties set
- Check field types match property types

```python
# ✅ Correct
@dataclass
class Config(BaseConfig):
    api_key: str = ""  # Will load from env property "api_key"

# ❌ Wrong
api_key: Optional[str] = None  # Optional not supported
```

#### 3. Queue Not Processing

**Symptom**: Messages queued but not processed

**Solutions**:
- Ensure `on_start()` creates queue processor task
- Check task isn't cancelled prematurely
- Verify queue.get() is being awaited
- Check for exceptions in processor loop

```python
async def on_start(self, ten_env):
    await super().on_start(ten_env)
    self.loop_task = asyncio.create_task(self._process_queue())
```

#### 4. Memory Leaks

**Symptom**: Memory grows over time

**Solutions**:
- Cancel tasks in `on_stop()`
- Clear queues on cleanup
- Remove event listeners
- Close file handles

```python
async def on_stop(self, ten_env):
    if self.task:
        self.task.cancel()
    await self.queue.flush()
    await super().on_stop(ten_env)
```

#### 5. Audio Frame Issues

**Symptom**: Audio is choppy or has errors

**Solutions**:
- Verify PCM parameters match actual data (sample rate, channels, bytes per sample)
- Ensure audio data is byte-aligned to frame boundaries
- Check for leftover bytes from previous frames
- Use `send_audio_out()` helper which handles alignment

```python
# Base class handles alignment automatically
await self.send_audio_out(
    ten_env,
    audio_data,
    sample_rate=16000,
    bytes_per_sample=2,  # 16-bit
    number_of_channels=1  # Mono
)
```

#### 6. Type Validation Errors

**Symptom**: Pydantic validation failures

**Solutions**:
- Check Pydantic model field types
- Ensure required fields are provided
- Validate data before creating model
- Use `.model_dump()` to serialize

```python
from ten_ai_base.struct import LLMRequest

try:
    request = LLMRequest(**data)
except ValidationError as e:
    print(f"Validation error: {e}")
```

### Debugging Tips

1. **Enable verbose logging**:
```python
await ten_env.log_category("debug", f"Processing: {data}")
```

2. **Use dumper utilities**:
```python
from ten_ai_base.dumper import dump_message
dump_message(message)  # Prints formatted message
```

3. **Check queue state**:
```python
print(f"Queue size: {self.queue.qsize()}")
```

4. **Inspect event emitter**:
```python
print(f"Listeners: {self.emitter._listeners}")
```

5. **Monitor task state**:
```python
if self.task and not self.task.done():
    print("Task is still running")
```

### Performance Optimization

1. **Use concurrent processing (LLM2)** for multiple requests
2. **Limit chat memory** to prevent unbounded growth
3. **Buffer audio frames** instead of sending individually
4. **Cancel tasks** when requests are aborted
5. **Use async generators** for streaming to avoid memory buildup

---

## Quick Reference

### Import Commonly Used Items

```python
from ten_ai_base import (
    # Base classes
    AsyncLLMBaseExtension,
    AsyncLLM2BaseExtension,
    AsyncTTSBaseExtension,
    AsyncTTS2BaseExtension,
    AsyncASRBaseExtension,
    AsyncMLLMBaseExtension,
    AsyncLLMToolBaseExtension,

    # Config
    BaseConfig,

    # Memory
    ChatMemory,
    AsyncChatMemory,

    # Helpers
    AsyncQueue,
    AsyncEventEmitter,
    TimeHelper,
    PCMWriter,

    # Types
    LLMToolMetadata,
    LLMCallCompletionArgs,
    LLMDataCompletionArgs,

    # Structs
    LLMRequest,
    LLMResponse,
    TTSTextInput,
    ASRResult,

    # Messages
    ModuleError,
    ModuleMetrics,
    ErrorMessage,
    MetricsMessage,

    # Timeline
    Timeline,

    # Usage
    LLMUsage,

    # Transcription
    UserTranscription,
    AssistantTranscription,
)
```

### Message Constants

```python
from ten_ai_base.const import (
    CMD_TOOL_REGISTER,
    CMD_TOOL_CALL,
    CMD_CHAT_COMPLETION_CALL,
    CMD_CHAT_COMPLETION,
    CMD_IN_FLUSH,

    DATA_IN_TEXT_DATA_CONTENT,
    DATA_OUT_TEXT_DATA,
)
```

### Standard Lifecycle

```python
class MyExtension(AsyncLLMBaseExtension):
    async def on_init(self, ten_env):
        await super().on_init(ten_env)
        # Initialize resources

    async def on_start(self, ten_env):
        await super().on_start(ten_env)
        # Load config, start tasks

    async def on_cmd(self, ten_env, cmd):
        # Handle commands
        pass

    async def on_data(self, ten_env, data):
        # Handle data messages
        pass

    async def on_stop(self, ten_env):
        # Cancel tasks, flush queues
        await super().on_stop(ten_env)

    async def on_deinit(self, ten_env):
        # Final cleanup
        await super().on_deinit(ten_env)
```

---

## Additional Resources

- **TEN Framework Docs**: [Check runtime documentation]
- **Integration Tests**: See `integration_tests/` for reference implementations
- **Type Definitions**: See `interface/ten_ai_base/types.py` for API contracts
- **Pydantic Models**: See `interface/ten_ai_base/struct.py` for data structures

---

## Version History

- **0.7.3** (Current) - TTS2 state machine improvements
- **0.7.x** - TTS2/LLM2 base classes added
- **0.6.x** - Initial async patterns established

---

**For AI Assistants**: When working with this codebase:
1. Always check existing base classes before creating new abstractions
2. Follow the async-first pattern consistently
3. Use BaseConfig for all configuration needs
4. Implement proper error handling with ModuleError
5. Track metrics for performance monitoring
6. Write integration tests for new extensions
7. Maintain backwards compatibility when modifying base classes
8. Document complex state machines clearly
9. Use type hints and Pydantic for validation
10. Test cleanup/cancellation paths thoroughly
