from dataclasses import dataclass, field
from enum import Enum
class MessageRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
@dataclass
class Message:
    role: str
    content: str
    images: tuple = ()
@dataclass
class ChatMessage:
    id: int
    role: MessageRole
    content: dict
@dataclass
class Hit:
    chunk_id: int
    document_id: str
    start_line: int
    end_line: int
    title: str
    content: str

@dataclass
class HardwareBudget:
    ram_available_bytes: int
